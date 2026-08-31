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


ORG_CACHE_FILE = BASE / "org_uuids.json"


def load_cached_org_uuids() -> dict:
    if ORG_CACHE_FILE.exists():
        try:
            return json.loads(ORG_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "BLR": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "MUM": "44cb587c-a690-44b5-94c2-37539500c7d5",
        "HYD": None
    }


def save_cached_org_uuid(code: str, uuid: str):
    try:
        cached = load_cached_org_uuids()
        cached[code] = uuid
        ORG_CACHE_FILE.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        Log.ok(f"Saved discovered Org UUID for {code}: {uuid} -> {ORG_CACHE_FILE.name}")
    except Exception as e:
        Log.warn(f"Note saving org UUID: {e}")


def switch_to_city(context: BrowserContext, main_page: Page, target: dict, previous_orgs: set) -> Page:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    code = target["code"]
    short = target["short_name"]
    acct = target["account_name"]

    cached_orgs = load_cached_org_uuids()
    org_uuid = target.get("org_uuid") or cached_orgs.get(code)
    Log.step("SWITCH", f"Opening {city} ('{short}')")

    # 1. Direct URL navigation if org_uuid is known
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        Log.info(f"Direct navigating to {city} URL: {url}...")
        try:
            main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
            Log.wait(4, f"Loading {city} promotions page")
            main_page = ensure_main_page(context, main_page)
            dismiss_banner(main_page)

            if f"/orgs/{org_uuid}" in main_page.url:
                exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
                if exp_btn.is_visible(timeout=5000):
                    Log.ok(f"Direct URL verified for {city} via Org UUID ({org_uuid})!")
                    return main_page
        except Exception as e:
            Log.warn(f"Direct navigation note: {e}")
            main_page = ensure_main_page(context, main_page)

    # 2. UI Switcher Navigation with JS Progressive Container Scrolling
    for attempt in range(1, 4):
        Log.info(f"Attempt {attempt}/3: Opening Account Switcher UI for {city}...")
        try:
            main_page = ensure_main_page(context, main_page)
            user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
            if not user_btn.is_visible(timeout=4000):
                main_page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first

            user_btn.click()
            Log.wait(1, "Opening user menu")

            sw_btn = main_page.locator('text="Switch account"').first
            if not sw_btn.is_visible(timeout=3000):
                Log.warn(f"'Switch account' option not visible in user menu on attempt {attempt}")
                continue

            sw_btn.click()
            Log.wait(2, "Opening account list")

            # Progressive Scroll & Smart Item Search inside the Switcher Container
            switch_result = main_page.evaluate("""(cityTarget) => {
                const isTarget = (txt) => {
                    const t = txt.toUpperCase();
                    if (cityTarget === 'HYD') {
                        // Match HYD P or Hyderabad P, strictly exclude HYD I, II, III, IV, V
                        if (!t.includes('HYD') && !t.includes('HYDERABAD')) return false;
                        if (!t.includes(' P') && !t.includes(' P.') && !t.includes(' PVT')) return false;
                        if (t.includes('HYD I') || t.includes('HYD II') || t.includes('HYD III') || t.includes('HYD IV') || t.includes('HYD V')) return false;
                        return true;
                    } else if (cityTarget === 'MUM') {
                        return (t.includes('MUM') || t.includes('MUMBAI')) && (t.includes(' P') || t.includes(' PVT')) && !t.includes('MUM I') && !t.includes('MUM II');
                    } else if (cityTarget === 'BLR') {
                        return (t.includes('BLR') || t.includes('BANGALORE')) && (t.includes(' P') || t.includes(' PVT'));
                    }
                    return false;
                };

                const allDivs = Array.from(document.querySelectorAll('div, ul, section'));
                const containers = allDivs.filter(el => {
                    const s = window.getComputedStyle(el);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                });
                const container = containers[containers.length - 1];

                // Scroll container to top first so items like HYD P are visible
                if (container) container.scrollTop = 0;

                const candidates = Array.from(document.querySelectorAll('div, li, button, span, [role="radio"], [role="menuitem"]'));
                for (let el of candidates) {
                    const txt = el.innerText ? el.innerText.trim() : '';
                    if (isTarget(txt) && txt.length < 80) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        el.click();
                        return { success: true, matchedText: txt };
                    }
                }

                if (container) {
                    for (let pos = 100; pos <= container.scrollHeight; pos += 100) {
                        container.scrollTop = pos;
                        for (let el of candidates) {
                            const txt = el.innerText ? el.innerText.trim() : '';
                            if (isTarget(txt) && txt.length < 80) {
                                el.scrollIntoView({ behavior: 'instant', block: 'center' });
                                el.click();
                                return { success: true, matchedText: txt };
                            }
                        }
                    }
                }

                return { success: false };
            }""", code)

            if switch_result.get("success"):
                Log.ok(f"Switcher clicked item: '{switch_result.get('matchedText')}'")
                time.sleep(6)  # Wait for navigation

            main_page = ensure_main_page(context, main_page)
            time.sleep(2)
            current_url = main_page.url

            new_org = None
            if "/orgs/" in current_url:
                new_org = current_url.split("/orgs/")[1].split("/")[0]

            # Anti-contamination check:
            if new_org and new_org not in previous_orgs:
                Log.ok(f"SUCCESS: Switched to {city}! Active Org UUID: {new_org}")
                save_cached_org_uuid(code, new_org)
                target["org_uuid"] = new_org

                promo_url = f"https://supplier.uber.com/orgs/{new_org}/promotions"
                if "/promotions" not in main_page.url:
                    main_page.goto(promo_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)

                dismiss_banner(main_page)
                return main_page
            else:
                Log.warn(f"Org UUID ({new_org}) still matches previous city ({previous_orgs})! Retrying switcher...")
                time.sleep(2)

        except Exception as e:
            Log.warn(f"Switcher attempt {attempt} note: {e}")
            time.sleep(2)

    raise RuntimeError(f"FATAL: Failed to switch to {city}. URL is still on previous city org ({main_page.url}). Aborting export to prevent data contamination!")


def export_and_download_city(context: BrowserContext, main_page: Page, target: dict, download_state: dict, seen_files: set = None) -> Path:
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

    if seen_files is None:
        seen_files = set()

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

        # 1. Check download state from context listener — skip if already seen
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            if str(download_state["latest_file"]) not in seen_files:
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
                    if str(f) in seen_files:
                        continue
                    try:
                        # Strict trigger_time check
                        if f.stat().st_mtime >= trigger_time and f.stat().st_size > 100:
                            if is_valid_incentive_file(f):
                                dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                if f != dest:
                                    shutil.copy2(str(f), str(dest))
                                found_file = dest
                                seen_files.add(str(f))
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
        seen_files: set = set()      # Track files claimed by previous cities — prevents cross-contamination
        previous_orgs: set = set()   # Track org UUIDs of prior cities — prevents export on wrong org

        for i, target in enumerate(TARGET_CITIES):
            main_page = switch_to_city(context, main_page, target, previous_orgs)
            time.sleep(2)
            # Refresh page 3x before clicking Export to clear stale state / leftover popup artefacts
            Log.info(f"Refreshing page 3x before Export for {target['city']}...")
            for r in range(1, 4):
                try:
                    main_page.reload(wait_until="domcontentloaded", timeout=30000)
                    Log.info(f"  Refresh {r}/3 complete")
                    time.sleep(3)
                except Exception as e:
                    Log.warn(f"  Refresh {r} note: {e}")
            # Reset download state so previous city's late event is not picked up
            download_state["latest_file"] = None
            csv_path = export_and_download_city(context, main_page, target, download_state, seen_files)
            if csv_path and csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df["City"] = target["city"]
                    all_city_dfs.append(df)
                except Exception:
                    pass
                # Record this city's org UUID so next city can't use it
                if target.get("org_uuid"):
                    previous_orgs.add(target["org_uuid"])
            # 30s cooldown between cities so popup tabs fully close and network settles
            if i < len(TARGET_CITIES) - 1:
                Log.info(f"Cooldown: 30s after {target['city']} download before proceeding...")
                for s in range(30, 0, -5):
                    Log.info(f"  Cooldown: {s}s remaining...")
                    time.sleep(5)

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
