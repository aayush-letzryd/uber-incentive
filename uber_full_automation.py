"""
LETZRYD · UBER OFFICIAL CSV EXPORT & CONSOLIDATION PIPELINE
Waits for official Uber CSV export downloads across Bangalore, Mumbai, and Hyderabad.
Produces clean individual CSV/Excel files and Consolidated 3-City Master Report.
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

# ==============================================================================
# CONFIGURATION
# ==============================================================================
TARGET_CITIES = [
    {
        "city": "Bangalore",
        "code": "BLR",
        "account_name": "SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P",
        "short_name": "BLR P",
        "file_keyword": "BLR_P"
    },
    {
        "city": "Mumbai",
        "code": "MUM",
        "account_name": "Samvreeddhi Mobility Pvt. Ltd. MUM P",
        "short_name": "MUM P",
        "file_keyword": "MUM_P"
    },
    {
        "city": "Hyderabad",
        "code": "HYD",
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "short_name": "HYD P",
        "file_keyword": "HYD_P"
    }
]

BASE        = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
SS_DIR      = BASE / "screenshots"
OUT_DIR     = BASE / "uber_reports"
COOKIES_F   = BASE / "cookies.json"
STATE_F     = BASE / "storage_state.json"
USER_DL_DIR = Path(r"C:\Users\anura\Downloads")

for d in [PROFILE_DIR, SS_DIR, OUT_DIR]:
    d.mkdir(exist_ok=True)


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


def load_session(context: BrowserContext) -> bool:
    if COOKIES_F.exists():
        try:
            cookies = json.loads(COOKIES_F.read_text())
            context.add_cookies(cookies)
            Log.ok(f"Loaded {len(cookies)} cached session cookies")
            return True
        except Exception as e:
            Log.warn(f"Cookie load note: {e}")
    return False


def dismiss_banner(page: Page):
    try:
        banner_close = page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first
        if banner_close.is_visible(timeout=1000):
            banner_close.click()
            time.sleep(1)
    except Exception:
        pass


def switch_account(page: Page, target: dict) -> bool:
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    Log.step("SWITCH", f"Switching account to {city} ('{short}')")

    dismiss_banner(page)

    user_btn = page.locator('[data-testid="user-menu-button"]').first
    if user_btn.is_visible(timeout=4000):
        user_btn.click()
        Log.wait(1, "Opening user menu")

        sw_btn = page.locator('text="Switch account"').first
        if sw_btn.is_visible(timeout=3000):
            sw_btn.click()
            Log.wait(2, "Opening account list")

            for query in [short, acct, city]:
                opt = page.locator(f'text="{query}"').last
                if opt.is_visible(timeout=1500):
                    opt.scroll_into_view_if_needed()
                    opt.click()
                    Log.ok(f"Selected {city} account ({query})")
                    Log.wait(5, f"Loading {city} dashboard")
                    return True

            Log.warn(f"Scrolling account list for '{short}'...")
            for _ in range(6):
                page.mouse.wheel(0, 350)
                time.sleep(0.5)
                opt = page.locator(f'text="{short}"').last
                if opt.is_visible(timeout=1000):
                    opt.click()
                    Log.ok(f"Selected {city} after scroll")
                    Log.wait(5, f"Loading {city} dashboard")
                    return True

            page.keyboard.press("Escape")
            Log.warn(f"Could not find '{short}' in switch menu")

    return False


def wait_for_new_export_file(keyword: str, trigger_time: float, max_wait_seconds: int = 600) -> Path:
    """
    Watches Downloads folder and OUT_DIR for a new CSV file containing keyword
    modified after trigger_time.
    """
    Log.info(f"Watching for newly downloaded CSV matching '*{keyword}*.csv' (timeout {max_wait_seconds}s)...")
    start = time.time()
    
    while time.time() - start < max_wait_seconds:
        elapsed = int(time.time() - start)
        
        # Check both Downloads and OUT_DIR
        for search_dir in [USER_DL_DIR, OUT_DIR]:
            if search_dir.exists():
                for p in search_dir.glob("*.csv"):
                    if "vehicle_incentives" in p.name.lower() and keyword.lower() in p.name.lower():
                        try:
                            mtime = p.stat().st_mtime
                            if mtime >= (trigger_time - 10) and p.stat().st_size > 0:
                                Log.ok(f"New Export File Detected: {p.name} ({p.stat().st_size:,} bytes)")
                                return p
                        except Exception:
                            pass

        if elapsed % 15 == 0 and elapsed > 0:
            Log.info(f"Still waiting for Uber backend export... ({elapsed}s / {max_wait_seconds}s)")
        time.sleep(3)

    Log.warn(f"Timed out after {max_wait_seconds}s waiting for {keyword} export.")
    return None


def trigger_export_and_download(page: Page, target: dict) -> Path:
    city = target["city"]
    code = target["code"]
    kw   = target["file_keyword"]
    today = datetime.datetime.now().strftime("%Y%m%d")
    Log.step("EXPORT", f"Triggering Official CSV Export for {city} ({code})")

    # Navigate to promotions tab
    dismiss_banner(page)
    curr_url = page.url
    if "/promotions" not in curr_url:
        org_id = curr_url.split("/orgs/")[1].split("/")[0] if "/orgs/" in curr_url else "ebb10afb-c08b-463e-a4fa-33b64674adfd"
        page.goto(f"https://supplier.uber.com/orgs/{org_id}/promotions", timeout=45000)
        Log.wait(5, "Loading promotions tab")

    dismiss_banner(page)

    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if not exp_btn.is_visible(timeout=4000):
        Log.err(f"Export button not visible on {city} promotions page!")
        return None

    # Track trigger time
    trigger_time = time.time()

    # Ensure no open overlays or menus intercept clicks
    try:
        page.keyboard.press("Escape")
        time.sleep(1)
    except Exception:
        pass

    # Click the Export button (force click / JS dispatch)
    Log.info(f"Clicking 'Export' button on {city} Promotions tab...")
    try:
        exp_btn.evaluate("btn => btn.click()")
    except Exception:
        exp_btn.click(force=True)
    Log.ok(f"Export triggered! Spinner active.")

    # Wait for the file to be generated and downloaded
    downloaded_file = wait_for_new_export_file(kw, trigger_time, max_wait_seconds=600)

    if downloaded_file and downloaded_file.exists():
        dest_csv = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
        dest_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.xlsx"

        # Copy to output folder
        shutil.copy2(str(downloaded_file), str(dest_csv))
        
        # Also convert to Excel
        try:
            df = pd.read_csv(dest_csv)
            df["City"] = city
            df.to_excel(dest_xlsx, index=False)
            Log.ok(f"Successfully saved {len(df):,} records for {city} -> {dest_xlsx.name}")
            return dest_csv
        except Exception as e:
            Log.warn(f"Excel conversion note: {e}")
            return dest_csv

    return None


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 75)
    print("   LETZRYD - UBER OFFICIAL EXPORT PIPELINE (3 CITIES)")
    print("   Bangalore | Mumbai | Hyderabad")
    print("=" * 75)

    cleanup_locks()

    with sync_playwright() as pw:
        Log.info("Launching Chrome with persistent user profile...")
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized"
            ]
        )

        # Listen globally on context for downloads / popups
        context.on("page", lambda p: Log.info(f"New popup/tab opened: {p.url[:60]}"))

        page = context.pages[0] if context.pages else context.new_page()
        load_session(context)

        Log.info("Opening Uber Supplier Promotions portal...")
        try:
            page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
            Log.wait(5, "Portal initial load")
        except Exception as e:
            Log.warn(f"Navigation: {e}")

        all_city_dfs = []
        downloaded_csvs = []

        # Iterate through all 3 target cities
        for target in TARGET_CITIES:
            switch_account(page, target)
            csv_path = trigger_export_and_download(page, target)
            if csv_path and csv_path.exists():
                downloaded_csvs.append(csv_path)
                try:
                    df = pd.read_csv(csv_path)
                    df["City"] = target["city"]
                    all_city_dfs.append(df)
                except Exception:
                    pass

        # Build Master 3-City Consolidated Report
        if all_city_dfs:
            today = datetime.datetime.now().strftime("%Y%m%d")
            master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
            master_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv"

            master_df = pd.concat(all_city_dfs, ignore_index=True)
            
            # Put City column first
            cols = ["City"] + [c for c in master_df.columns if c != "City"]
            master_df = master_df[cols]

            master_df.to_excel(master_xlsx, index=False)
            master_df.to_csv(master_csv, index=False)

            Log.ok("=" * 70)
            Log.ok(f" MASTER CONSOLIDATED REPORT GENERATED SUCCESSFULLY!")
            Log.ok(f" File: {master_xlsx}")
            Log.ok(f" Total Rows Across All 3 Cities: {len(master_df):,}")
            Log.ok("=" * 70)

        Log.wait(5, "Closing browser session")
        context.close()


if __name__ == "__main__":
    main()
