"""Test extracting all fields from role='row' across pages."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path
import pandas as pd

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"
SS_DIR      = Path(__file__).parent / "screenshots"

with sync_playwright() as pw:
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

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
    time.sleep(5)

    # Close top banner
    try:
        page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first.click()
        time.sleep(1)
    except Exception:
        pass

    # Extract all rows on current page
    rows = page.locator('div[role="row"]').all()
    print(f"Total role='row' elements found: {len(rows)}")

    extracted_records = []
    for i, r in enumerate(rows):
        txt = r.inner_text().strip()
        lines = [line.strip() for line in txt.split('\n') if line.strip()]
        print(f"\n--- ROW {i} (lines: {len(lines)}) ---")
        print(lines)
        if len(lines) >= 4 and not "Vehicle / ID" in lines[0]:
            extracted_records.append(lines)

    print(f"\nTotal vehicle records parsed: {len(extracted_records)}")
    time.sleep(2)
    context.close()
