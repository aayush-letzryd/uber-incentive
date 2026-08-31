"""Test Export button behavior and table pagination."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path
import pandas as pd

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"
SS_DIR      = Path(__file__).parent / "screenshots"
OUT_DIR     = Path(__file__).parent / "uber_reports"

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
    
    # Listen to all network responses and downloads
    page.on("download", lambda dl: print(f"DOWNLOAD TRIGGERED: {dl.suggested_filename}"))
    page.on("response", lambda res: print(f"API RESPONSE: {res.url[:100]} ({res.status})") if "promotion" in res.url.lower() or "export" in res.url.lower() or "report" in res.url.lower() else None)

    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
    time.sleep(5)

    # Click Export button
    print("\nClicking Export button...")
    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if exp_btn.is_visible():
        exp_btn.click()
        time.sleep(3)
        page.screenshot(path=str(SS_DIR / "after_export_click.png"))
        print("Screenshot saved: after_export_click.png")

        # Check if modal or toast popped up
        toasts = page.locator('[role="alert"], [data-testid*="toast"], [data-testid*="modal"], [role="dialog"]').all()
        for t in toasts:
            try:
                print(f"Toast/Modal: {t.inner_text().strip()}")
            except Exception:
                pass

    # Test clicking the first vehicle row to see breakdown
    print("\nClicking first vehicle row...")
    first_row = page.locator('table tbody tr, [role="row"]').first
    if first_row.is_visible():
        first_row.click()
        time.sleep(2)
        page.screenshot(path=str(SS_DIR / "vehicle_row_details.png"))
        print("Screenshot saved: vehicle_row_details.png")

    time.sleep(4)
    context.close()
