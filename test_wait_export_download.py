"""
Test script to click Export on Bangalore (or current org) and WAIT until the browser download completes.
Logs progress every 5 seconds while Uber generates the file on backend.
"""

import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path
import pandas as pd

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"
OUT_DIR     = Path(__file__).parent / "uber_reports"
SS_DIR      = Path(__file__).parent / "screenshots"

OUT_DIR.mkdir(exist_ok=True)
SS_DIR.mkdir(exist_ok=True)

with sync_playwright() as pw:
    print("=" * 60)
    print("   TESTING EXPORT DOWNLOAD WITH EXTENDED WAIT TIME")
    print("=" * 60)

    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=False,
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled", "--disable-infobars"],
    )

    if COOKIES_F.exists():
        cookies = json.loads(COOKIES_F.read_text())
        context.add_cookies(cookies)
        print(f"Loaded {len(cookies)} cookies.")

    page = context.pages[0] if context.pages else context.new_page()
    url = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions"
    print(f"Opening {url}...")
    page.goto(url, timeout=45000)
    time.sleep(5)

    # Dismiss top banner if present
    try:
        page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first.click()
        time.sleep(1)
    except Exception:
        pass

    # Find Export button
    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if not exp_btn.is_visible():
        print("Export button not found! Taking screenshot...")
        page.screenshot(path=str(SS_DIR / "export_missing.png"))
        context.close()
        sys.exit(1)

    print("Found Export button! Clicking and waiting for download event (up to 3 minutes)...")
    
    download_received = None

    def on_dl(dl):
        global download_received
        download_received = dl
        print(f"\n>>> DOWNLOAD EVENT FIRED: {dl.suggested_filename} <<<")

    page.on("download", on_dl)

    # Click the Export button
    exp_btn.click()
    print("Clicked Export button. Now waiting for backend generation...")

    # Wait loop up to 180 seconds
    start_time = time.time()
    max_wait = 180
    saved_file_path = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        if download_received:
            dest = OUT_DIR / download_received.suggested_filename
            download_received.save_as(str(dest))
            saved_file_path = dest
            print(f"\n[+] FILE DOWNLOADED SUCCESSFULLY: {dest} ({dest.stat().st_size} bytes)")
            break

        # Check if button is still spinning
        page.screenshot(path=str(SS_DIR / "export_waiting.png"))
        print(f"  [~] Waiting for download... ({elapsed}s / {max_wait}s)")
        time.sleep(5)

    if saved_file_path and saved_file_path.exists():
        print("\n=======================================================")
        print("   EXPORT DOWNLOAD COMPLETE - INSPECTING DATA")
        print("=======================================================")
        try:
            if saved_file_path.suffix.lower() == '.xlsx':
                df = pd.read_excel(saved_file_path)
            else:
                df = pd.read_csv(saved_file_path)
            print(f"Total Rows in Downloaded File: {len(df)}")
            print(f"Columns: {list(df.columns)}")
            print("\nFirst 5 Rows:")
            print(df.head(5).to_string())
        except Exception as e:
            print(f"Error reading downloaded file: {e}")
    else:
        print("\n[-] No download event was triggered within 3 minutes.")
        print("Checking if Uber shows a notification/toast or requires checking reports tab...")
        page.screenshot(path=str(SS_DIR / "export_timeout.png"))

    print("\nClosing browser in 5 seconds...")
    time.sleep(5)
    context.close()
