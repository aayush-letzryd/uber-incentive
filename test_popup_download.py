"""
LETZRYD · MUMBAI POPUP DOWNLOAD CAPTURE
Captures the ephemeral popup tab triggered by the Export button and gets the download.
"""

import sys, io, time, json, datetime
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
    log("   MUMBAI POPUP TAB DOWNLOAD CAPTURE")
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

        # Capture any download across any page in context
        downloaded_file = {"path": None}

        def on_page(new_page):
            log(f"⚡ Ephemeral popup tab opened: {new_page.url}")
            new_page.on("download", lambda dl: handle_download(dl))

        def handle_download(dl):
            log(f"\n🔥🔥 DOWNLOAD RECEIVED: {dl.suggested_filename} 🔥🔥")
            dest = OUT_DIR / dl.suggested_filename
            dl.save_as(str(dest))
            downloaded_file["path"] = dest
            log(f"✅ Saved to: {dest} ({dest.stat().st_size:,} bytes)")

        context.on("page", on_page)
        page.on("download", handle_download)

        log("1. Navigating to Mumbai Promotions...")
        page.goto(MUMBAI_PROMO_URL, timeout=45000)
        time.sleep(6)

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

        log("2. Clicking Export button...")
        try:
            exp_btn.evaluate("b => b.click()")
        except Exception:
            exp_btn.click(force=True)

        log("3. Waiting for backend generation & popup download (up to 240s)...")
        start = time.time()
        while time.time() - start < 240:
            if downloaded_file["path"] and downloaded_file["path"].exists() and downloaded_file["path"].stat().st_size > 0:
                log(f"Download complete! Waited {int(time.time() - start)}s.")
                break
            time.sleep(3)

        saved = downloaded_file["path"]
        if saved and saved.exists():
            log("==========================================================")
            log("🎉 SUCCESS! MUMBAI OFFICIAL CSV EXPORT SAVED")
            log(f"📁 Path: {saved} ({saved.stat().st_size:,} bytes)")
            log("==========================================================")
            try:
                # Read lines to verify valid CSV
                with open(saved, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [l.strip() for l in f if l.strip()][:5]
                log(f"Header: {lines[0] if lines else 'Empty'}")
                if len(lines) > 1:
                    log(f"Sample Row: {lines[1]}")
            except Exception as e:
                log(f"Read note: {e}")
        else:
            log("[-] No file was downloaded.")

        time.sleep(3)
        context.close()

if __name__ == "__main__":
    main()
