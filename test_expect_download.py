"""
LETZRYD · MUMBAI EXPORT STREAM FLUSH TEST
Waits for full download stream completion before saving and closing.
"""

import sys, io, time, json, datetime, shutil
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
from playwright.sync_api import sync_playwright
import pandas as pd

BASE        = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
SS_DIR      = BASE / "screenshots"
OUT_DIR     = BASE / "uber_reports"
COOKIES_F   = BASE / "cookies.json"

MUMBAI_PROMO_URL = "https://supplier.uber.com/orgs/44cb587c-a690-44b5-94c2-37539500c7d5/promotions"

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def cleanup_locks():
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass

def main():
    log("==========================================================")
    log("   TESTING MUMBAI EXPORT STREAM COMPLETION")
    log("==========================================================")

    cleanup_locks()

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            downloads_path=str(OUT_DIR),
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars"]
        )

        if COOKIES_F.exists():
            cookies = json.loads(COOKIES_F.read_text())
            context.add_cookies(cookies)

        page = context.pages[0] if context.pages else context.new_page()

        log("1. Opening Mumbai Promotions...")
        page.goto(MUMBAI_PROMO_URL, timeout=45000)
        time.sleep(5)

        # Dismiss banner if present
        try:
            page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first.click()
            time.sleep(1)
        except Exception:
            pass

        exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
        if not exp_btn.is_visible():
            log("❌ Export button not found!")
            context.close()
            return

        log("2. Clicking Export and waiting on page.expect_download()...")
        with page.expect_download(timeout=120000) as dl_info:
            try:
                exp_btn.evaluate("b => b.click()")
            except Exception:
                exp_btn.click(force=True)
            log("   Export clicked, waiting for download stream...")

        download = dl_info.value
        log(f"\n🔥🔥 DOWNLOAD EVENT RECEIVED: {download.suggested_filename} 🔥🔥")
        
        # Wait for file to finish downloading completely
        temp_file = download.path()
        log(f"Temp file downloaded: {temp_file} ({Path(temp_file).stat().st_size:,} bytes)")

        final_dest = OUT_DIR / download.suggested_filename
        download.save_as(str(final_dest))
        log(f"✅ Saved official CSV: {final_dest} ({final_dest.stat().st_size:,} bytes)")

        # Verify contents
        time.sleep(1)
        try:
            df = pd.read_csv(final_dest)
            log(f"📊 Total Rows: {len(df):,}")
            log(f"📋 Columns: {list(df.columns)}")
            log("\nFirst 3 Rows:")
            print(df.head(3).to_string(), flush=True)

            # Create Excel copy
            xlsx_path = OUT_DIR / final_dest.with_suffix(".xlsx").name
            df["City"] = "Mumbai"
            df.to_excel(xlsx_path, index=False)
            log(f"✅ Excel created: {xlsx_path.name}")
        except Exception as e:
            log(f"CSV read error: {e}")

        time.sleep(3)
        context.close()

if __name__ == "__main__":
    main()
