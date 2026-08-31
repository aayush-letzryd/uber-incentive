"""
LETZRYD · UBER OFFICIAL EXPORT & DOWNLOAD PIPELINE (PRODUCTION v4.8)
====================================================================
- Stable browser lifecycle with popup tab isolation
- Downloads captured via context.on('download')
- Sequential processing of Bangalore, Mumbai, Hyderabad
- Builds Master Consolidated Excel
"""

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
import time
import json
import glob
import shutil
import datetime
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from playwright_stealth import Stealth

# ==============================================================================
# CONFIGURATION
# ==============================================================================
TARGET_CITIES = [
    {
        "city": "Bangalore",
        "code": "BLR",
        "org_uuid": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "account_name": "SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P",
        "short_name": "BLR P",
        "file_keyword": "BLR_P",
        "max_wait_seconds": 900
    },
    {
        "city": "Mumbai",
        "code": "MUM",
        "org_uuid": "44cb587c-a690-44b5-94c2-37539500c7d5",
        "account_name": "Samvreeddhi Mobility Pvt. Ltd. MUM P",
        "short_name": "MUM P",
        "file_keyword": "MUM_P",
        "max_wait_seconds": 600
    },
    {
        "city": "Hyderabad",
        "code": "HYD",
        "org_uuid": None,
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "short_name": "HYD P",
        "file_keyword": "HYD_P",
        "max_wait_seconds": 600
    }
]

BASE        = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
SS_DIR      = BASE / "screenshots"
OUT_DIR     = BASE / "uber_reports"
COOKIES_F   = BASE / "cookies.json"
STATE_F     = BASE / "storage_state.json"
USER_DL_DIR = Path(os.getenv("DOWNLOADS_DIR", str(Path.home() / "Downloads")))

for d in [PROFILE_DIR, SS_DIR, OUT_DIR, USER_DL_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class Log:
    CYAN   = "\033[96m"; BOLD  = "\033[1m"
    GREEN  = "\033[92m"; WARN  = "\033[93m"
    RED    = "\033[91m"; RESET = "\033[0m"
    BLUE   = "\033[94m"

    @staticmethod
    def _t(): return datetime.datetime.now().strftime("%H:%M:%S")

    @classmethod
    def step(cls, n, msg):
        print(f"\n{cls.BOLD}{cls.CYAN}==> [STEP {n}] {msg}{cls.RESET}", flush=True)

    @classmethod
    def info(cls, msg):
        print(f"{cls.BLUE}  [*] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def ok(cls, msg):
        print(f"{cls.GREEN}  [+] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def warn(cls, msg):
        print(f"{cls.WARN}  [!] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def err(cls, msg):
        print(f"{cls.RED}  [-] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def wait(cls, secs, reason=""):
        txt = f"Waiting {secs}s" + (f" ({reason})" if reason else "")
        print(f"{cls.BLUE}  [~] {cls._t()} | {txt}{cls.RESET}", flush=True)
        time.sleep(secs)


def cleanup_locks():
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass


def ensure_main_page(context: BrowserContext, main_page: Page) -> Page:
    for p in list(context.pages):
        if p != main_page:
            try:
                if not p.is_closed():
                    p.close()
            except Exception:
                pass
    
    if main_page is None or main_page.is_closed():
        pages = [p for p in context.pages if not p.is_closed()]
        if pages:
            main_page = pages[0]
        else:
            main_page = context.new_page()
    
    return main_page


def load_session(context: BrowserContext) -> bool:
    if COOKIES_F.exists():
        try:
            cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
            Log.ok(f"Loaded {len(cookies)} cached session cookies")
            return True
        except Exception as e:
            Log.warn(f"Cookie load note: {e}")
    return False


def dismiss_banner(page: Page):
    try:
        if not page.is_closed():
            banner_close = page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first
            if banner_close.is_visible(timeout=1500):
                banner_close.click()
                time.sleep(1)
    except Exception:
        pass


def is_valid_incentive_file(file_path: Path) -> bool:
    try:
        if not file_path.exists() or file_path.stat().st_size < 100:
            return False
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            header = f.readline()
            return "Vehicle name" in header and "Number plate" in header
    except Exception:
        return False


def switch_to_city(context: BrowserContext, main_page: Page, target: dict) -> Page:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    org_uuid = target.get("org_uuid")
    Log.step("SWITCH", f"Opening {city} ('{short}')")

    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        Log.info(f"Navigating to {city} URL: {url}...")
        try:
            main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
            Log.wait(4, f"Loading {city} promotions page")
            main_page = ensure_main_page(context, main_page)
            dismiss_banner(main_page)

            exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
            if exp_btn.is_visible(timeout=5000):
                Log.ok(f"Direct URL verified for {city}!")
                return main_page
        except Exception as e:
            Log.warn(f"Direct navigation note: {e}")
            main_page = ensure_main_page(context, main_page)

    # Fallback to UI switcher
    Log.info(f"Using Account Switcher UI for {city}...")
    try:
        main_page = ensure_main_page(context, main_page)
        user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
        if user_btn.is_visible(timeout=4000):
            user_btn.click()
            Log.wait(1, "Opening user menu")
            
            sw_btn = main_page.locator('text="Switch account"').first
            if sw_btn.is_visible(timeout=3000):
                sw_btn.click()
                Log.wait(2, "Opening account list")

                for query in [acct, short, f"SAMVREEDDHI MOBILITY {short}", f"Samvreeddhi Mobility Pvt Ltd {short}"]:
                    opt = main_page.locator(f'text="{query}"').first
                    if opt.is_visible(timeout=1500):
                        try:
                            opt.scroll_into_view_if_needed()
                            opt.click()
                            Log.ok(f"Selected {city} ({query}) from switcher")
                            Log.wait(4, f"Loading {city} dashboard")
                            break
                        except Exception:
                            pass

        main_page = ensure_main_page(context, main_page)
        if "/promotions" not in main_page.url:
            if "/orgs/" in main_page.url:
                current_org = main_page.url.split("/orgs/")[1].split("/")[0]
                promo_url = f"https://supplier.uber.com/orgs/{current_org}/promotions"
                main_page.goto(promo_url, timeout=30000, wait_until="domcontentloaded")
                Log.wait(3, f"Opening Promotions tab: {promo_url}")
            else:
                promo_tab = main_page.locator('a:has-text("Promotions"), nav a[href*="promotions"]').first
                if promo_tab.is_visible(timeout=3000):
                    promo_tab.click()
                    Log.wait(3, "Opening Promotions tab")

        dismiss_banner(main_page)
        return main_page

    except Exception as e:
        Log.warn(f"Account switch note for {city}: {e}")
        return ensure_main_page(context, main_page)


def export_and_download_city(context: BrowserContext, main_page: Page, target: dict, download_state: dict) -> Path:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    code = target["code"]
    kw   = target["file_keyword"]
    max_wait = target.get("max_wait_seconds", 900)
    today = datetime.datetime.now().strftime("%Y%m%d")
    Log.step("EXPORT", f"Triggering Official Export & Download for {city} ({code})")

    dismiss_banner(main_page)

    exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=2000):
        try:
            ss_path = SS_DIR / f"missing_export_{code.lower()}.png"
            main_page.screenshot(path=str(ss_path))
        except Exception:
            pass
        Log.err(f"Export button not visible on {city} Promotions page! (URL: {main_page.url})")
        return None

    download_state["latest_file"] = None
    trigger_time = time.time()
    Log.info(f"Clicking 'Export' button for {city}...")
    try:
        exp_btn.evaluate("b => b.click()")
    except Exception:
        exp_btn.click(force=True)

    Log.ok(f"Export triggered! Monitoring download (up to {max_wait//60} mins)...")

    start_time = time.time()
    last_log = time.time()
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        if download_state.get("latest_file") and download_state["latest_file"].exists():
            if is_valid_incentive_file(download_state["latest_file"]):
                found_file = download_state["latest_file"]
                break

        # 2. Scan OUT_DIR and USER_DL_DIR — catch .csv AND UUID-named files (no extension)
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.iterdir():
                    if not f.is_file():
                        continue
                    if f.suffix in [".crdownload", ".tmp", ".part"]:
                        continue
                    try:
                        if f.stat().st_mtime >= (trigger_time - 5) and f.stat().st_size > 100:
                            if is_valid_incentive_file(f):
                                dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                if f != dest:
                                    shutil.copy2(str(f), str(dest))
                                found_file = dest
                                break
                    except Exception:
                        pass
            if found_file:
                break

        if found_file:
            break

        if time.time() - last_log >= 15:
            last_log = time.time()
            mins = elapsed // 60
            secs = elapsed % 60
            Log.info(f"Still waiting on Uber backend export... ({mins}m {secs}s / {max_wait//60}m)")

        time.sleep(2)

    # Let any popup tab finish and close cleanly
    time.sleep(3)
    ensure_main_page(context, main_page)

    if found_file and found_file.exists():
        dest_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
        dest_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.xlsx"

        if found_file != dest_csv:
            shutil.copy2(str(found_file), str(dest_csv))

        try:
            df = pd.read_csv(dest_csv)
            df["City"] = city
            df.to_excel(dest_xlsx, index=False)
            Log.ok(f"✅ Saved official dataset ({len(df):,} rows) -> {dest_xlsx.name}")
            return dest_csv
        except Exception as e:
            Log.warn(f"Excel conversion note: {e}")
            return dest_csv

    Log.warn(f"Timed out after {max_wait}s waiting for {city} export.")
    return None


def get_browser_launch_config():
    is_container = (
        os.path.exists("/.dockerenv")
        or os.getenv("K_SERVICE") is not None
        or os.getenv("CONTAINER") == "true"
        or sys.platform.startswith("linux")
    )
    
    headless_env = os.getenv("HEADLESS")
    if headless_env is not None:
        headless = headless_env.lower() in ("true", "1", "yes")
    else:
        headless = is_container

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-default-browser-check",
        "--lang=en-IN,en"
    ]

    if headless:
        args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ])

    return headless, args


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 75)
    print("   LETZRYD - UBER OFFICIAL EXPORT & DOWNLOAD ENGINE (3 CITIES)")
    print("   Bangalore | Mumbai | Hyderabad")
    print("=" * 75)

    cleanup_locks()
    headless, args = get_browser_launch_config()
    download_state = {"latest_file": None}

    with sync_playwright() as pw:
        Log.info(f"Launching Browser (Headless: {headless})...")
        
        launch_kwargs = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": headless,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "accept_downloads": True,
            "downloads_path": str(OUT_DIR),
            "ignore_default_args": ["--enable-automation"],
            "args": args
        }

        context = pw.chromium.launch_persistent_context(**launch_kwargs)

        def on_context_download(download):
            Log.ok(f"📥 Context Download Event: {download.suggested_filename}")
            dest = OUT_DIR / download.suggested_filename
            try:
                download.save_as(str(dest))
                download_state["latest_file"] = dest
                Log.ok(f"✅ Download saved: {dest.name} ({dest.stat().st_size:,} bytes)")
            except Exception as e:
                Log.warn(f"Download save_as note: {e}")

        context.on("download", on_context_download)

        main_page = context.pages[0] if context.pages else context.new_page()
        
        try:
            Stealth().apply_stealth_sync(main_page)
            Log.ok("Stealth mode active")
        except Exception as e:
            Log.warn(f"Stealth apply note: {e}")

        load_session(context)

        all_city_dfs = []
        today = datetime.datetime.now().strftime("%Y%m%d")

        for target in TARGET_CITIES:
            main_page = switch_to_city(context, main_page, target)
            time.sleep(2)
            csv_path = export_and_download_city(context, main_page, target, download_state)
            if csv_path and csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df["City"] = target["city"]
                    all_city_dfs.append(df)
                except Exception:
                    pass

        if all_city_dfs:
            master_df = pd.concat(all_city_dfs, ignore_index=True)
            master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
            master_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv"

            cols = ["City"] + [c for c in master_df.columns if c != "City"]
            master_df = master_df[cols]

            master_df.to_excel(master_xlsx, index=False)
            master_df.to_csv(master_csv, index=False)

            Log.ok("=" * 70)
            Log.ok(f"🎉 MASTER CONSOLIDATED REPORT GENERATED SUCCESSFULLY!")
            Log.ok(f"📁 Excel: {master_xlsx}")
            Log.ok(f"📊 Total Rows Across All 3 Cities: {len(master_df):,}")
            Log.ok("=" * 70)

        Log.info("Closing browser in 5 seconds...")
        time.sleep(5)
        context.close()


if __name__ == "__main__":
    main()
