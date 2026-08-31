"""
LETZRYD · UBER OFFICIAL EXPORT & DOWNLOAD PIPELINE (PRODUCTION v4.6)
====================================================================
1. Dynamic page lifecycle manager (`get_active_page`)
2. `context.on("download")` captures popup tab downloads
3. Instant CSV content validator
4. Multi-city aggregation across Bangalore, Mumbai, and Hyderabad
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
        "org_uuid": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
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


def get_active_page(context: BrowserContext) -> Page:
    active_pages = [p for p in context.pages if not p.is_closed()]
    if active_pages:
        return active_pages[0]
    return context.new_page()


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


def switch_to_city(context: BrowserContext, target: dict) -> Page:
    page = get_active_page(context)
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    org_uuid = target.get("org_uuid")
    Log.step("SWITCH", f"Opening {city} ('{short}')")

    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        Log.info(f"Navigating to {city} URL: {url}...")
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            Log.wait(4, f"Loading {city} promotions page")
            page = get_active_page(context)
            dismiss_banner(page)

            exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
            if exp_btn.is_visible(timeout=5000):
                Log.ok(f"Direct URL verified for {city}!")
                return page
        except Exception as e:
            Log.warn(f"Direct navigation note: {e}")
            page = get_active_page(context)

    # Fallback to UI switcher
    Log.info(f"Using Account Switcher UI for {city}...")
    try:
        page = get_active_page(context)
        user_btn = page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
        if user_btn.is_visible(timeout=4000):
            user_btn.click()
            Log.wait(1, "Opening user menu")
            
            sw_btn = page.locator('text="Switch account"').first
            if sw_btn.is_visible(timeout=3000):
                sw_btn.click()
                Log.wait(2, "Opening account list")

                for query in [acct, short, city]:
                    group = page.locator(f'div:has-text("{query}"), li:has-text("{query}"), span:has-text("{query}")').first
                    if group.is_visible(timeout=1500):
                        group.click()
                        time.sleep(1)
                        break

                for query in [acct, short]:
                    opt = page.locator(f'text="{query}"').last
                    if opt.is_visible(timeout=1500):
                        opt.scroll_into_view_if_needed()
                        opt.click()
                        Log.ok(f"Selected {city} ({query}) from switcher")
                        Log.wait(4, f"Loading {city} dashboard")
                        break

        page = get_active_page(context)
        if "/promotions" not in page.url:
            promo_tab = page.locator('a:has-text("Promotions"), nav a[href*="promotions"]').first
            if promo_tab.is_visible(timeout=3000):
                promo_tab.click()
                Log.wait(3, "Opening Promotions tab")

        dismiss_banner(page)
        return page

    except Exception as e:
        Log.warn(f"Account switch note for {city}: {e}")
        return get_active_page(context)


def export_and_download_city(context: BrowserContext, target: dict, download_state: dict) -> Path:
    page = get_active_page(context)
    city = target["city"]
    code = target["code"]
    kw   = target["file_keyword"]
    max_wait = target.get("max_wait_seconds", 900)
    today = datetime.datetime.now().strftime("%Y%m%d")
    Log.step("EXPORT", f"Triggering Official Export & Download for {city} ({code})")

    dismiss_banner(page)

    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=2000):
        ss_path = SS_DIR / f"missing_export_{code.lower()}.png"
        page.screenshot(path=str(ss_path))
        Log.err(f"Export button not visible on {city} Promotions page! (URL: {page.url})")
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
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        # 1. Check download state from context listener
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            found_file = download_state["latest_file"]
            break

        # 2. Scan OUT_DIR and USER_DL_DIR
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.glob("*"):
                    if f.is_file() and (f.suffix in [".csv", ".crdownload"] or "vehicle_incentives" in f.name.lower()):
                        try:
                            if f.stat().st_mtime >= (trigger_time - 5) and f.stat().st_size > 100:
                                if is_valid_incentive_file(f):
                                    dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                    shutil.copy2(str(f), str(dest))
                                    found_file = dest
                                    break
                        except Exception:
                            pass
            if found_file:
                break

        if found_file:
            break

        if elapsed % 15 == 0 and elapsed > 0:
            mins = elapsed // 60
            secs = elapsed % 60
            Log.info(f"Still waiting on Uber backend export... ({mins}m {secs}s / {max_wait//60}m)")

        time.sleep(2)

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

    channel = None if (is_container or headless) else "chrome"
    return headless, channel, args


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 75)
    print("   LETZRYD - UBER OFFICIAL EXPORT & DOWNLOAD ENGINE (3 CITIES)")
    print("   Bangalore | Mumbai | Hyderabad")
    print("=" * 75)

    cleanup_locks()
    headless, channel, args = get_browser_launch_config()
    download_state = {"latest_file": None}

    with sync_playwright() as pw:
        Log.info(f"Launching Browser (Headless: {headless}, Channel: {channel or 'bundled-chromium'})...")
        
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
        if channel:
            launch_kwargs["channel"] = channel

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

        page = get_active_page(context)
        
        try:
            Stealth().apply_stealth_sync(page)
            Log.ok("Stealth mode active")
        except Exception as e:
            Log.warn(f"Stealth apply note: {e}")

        load_session(context)

        all_city_dfs = []
        today = datetime.datetime.now().strftime("%Y%m%d")

        for target in TARGET_CITIES:
            page = switch_to_city(context, target)
            time.sleep(2)
            csv_path = export_and_download_city(context, target, download_state)
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
