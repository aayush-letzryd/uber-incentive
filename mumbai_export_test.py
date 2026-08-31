"""
LETZRYD · MUMBAI DIRECT ORG EXPORT & DOWNLOAD
Navigates directly to Mumbai org UUID (44cb587c-a690-44b5-94c2-37539500c7d5),
clicks Export, and saves the downloaded official CSV.
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
USER_DL_DIR = Path(r"C:\Users\anura\Downloads")

MUMBAI_PROMO_URL = "https://supplier.uber.com/orgs/44cb587c-a690-44b5-94c2-37539500c7d5/promotions"

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def ss(page, name):
    p = SS_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(p))
        log(f"📸 Screenshot: {name}.png")
    except Exception:
        pass

def cleanup_locks():
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass

def main():
    log("==========================================================")
    log("   TESTING DIRECT MUMBAI EXPORT & DOWNLOAD")
    log("==========================================================")

    cleanup_locks()

    with sync_playwright() as pw:
        log("1. Launching Chrome...")
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
            log(f"Loaded {len(cookies)} cookies.")

        page = context.pages[0] if context.pages else context.new_page()

        # Track downloads
        download_info = {"file": None, "url": None}

        def on_dl(dl):
            log(f"\n🔥🔥 DOWNLOAD CAUGHT: {dl.suggested_filename} 🔥🔥")
            dest = OUT_DIR / dl.suggested_filename
            dl.save_as(str(dest))
            download_info["file"] = dest
            download_info["url"] = dl.url
            log(f"✅ Saved downloaded CSV to: {dest} ({dest.stat().st_size:,} bytes)")

        page.on("download", on_dl)
        context.on("page", lambda p: p.on("download", on_dl))

        log(f"2. Navigating directly to Mumbai Promotions: {MUMBAI_PROMO_URL}...")
        page.goto(MUMBAI_PROMO_URL, timeout=45000)
        time.sleep(6)
        ss(page, "mumbai_direct_01_loaded")

        # Dismiss banner if present
        try:
            page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first.click()
            time.sleep(1)
        except Exception:
            pass

        # 3. Find and click Export
        log("3. Looking for Export button on Mumbai Promotions...")
        exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
        if not exp_btn.is_visible():
            log("❌ Export button not visible!")
            ss(page, "mumbai_direct_error_no_export")
            context.close()
            return

        trigger_time = time.time()
        log("4. Clicking Export button on Mumbai...")
        try:
            exp_btn.evaluate("btn => btn.click()")
        except Exception:
            exp_btn.click(force=True)

        log("✅ Export clicked! Waiting for download...")
        ss(page, "mumbai_direct_02_export_clicked")

        # 5. Monitor for download event or new file on disk
        max_wait = 180
        found_file = None

        for elapsed in range(0, max_wait, 3):
            if download_info["file"] and download_info["file"].exists():
                found_file = download_info["file"]
                break

            for search_dir in [USER_DL_DIR, OUT_DIR]:
                for f in search_dir.glob("*.csv"):
                    if "vehicle_incentives" in f.name.lower() and "mum" in f.name.lower():
                        try:
                            if f.stat().st_mtime >= (trigger_time - 10) and f.stat().st_size > 0:
                                log(f"🎯 Picked up newly downloaded file from disk: {f.name}")
                                dest = OUT_DIR / f.name
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
                log(f"   Waiting for export download... ({elapsed}s / {max_wait}s)")
                ss(page, "mumbai_direct_03_waiting")

            time.sleep(3)

        if found_file and found_file.exists():
            log("==========================================================")
            log("🎉 SUCCESS! MUMBAI OFFICIAL CSV DOWNLOADED")
            log(f"📁 Path: {found_file} ({found_file.stat().st_size:,} bytes)")
            log("==========================================================")
            try:
                df = pd.read_csv(found_file)
                log(f"Total Rows: {len(df):,}")
                log(f"Columns: {list(df.columns)}")
                log("\nSample 3 Rows:")
                print(df.head(3).to_string(), flush=True)

                xlsx_path = OUT_DIR / found_file.with_suffix(".xlsx").name
                df["City"] = "Mumbai"
                df.to_excel(xlsx_path, index=False)
                log(f"✅ Excel copy created: {xlsx_path}")
            except Exception as e:
                log(f"File inspection note: {e}")
        else:
            log("[-] No download occurred within timeout.")
            ss(page, "mumbai_direct_04_timeout")

        log("Closing browser...")
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    main()
