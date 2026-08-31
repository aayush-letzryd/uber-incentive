"""Test Switch account and table data scraping."""
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
    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
    time.sleep(5)

    # Click user menu
    print("1. Opening User Menu...")
    page.locator('[data-testid="user-menu-button"]').click()
    time.sleep(1)

    # Click Switch account
    print("2. Clicking 'Switch account'...")
    page.locator('text="Switch account"').click()
    time.sleep(2)
    page.screenshot(path=str(SS_DIR / "switch_account_list.png"))
    print("Screenshot saved: switch_account_list.png")

    # List all account options visible
    print("\nAccount options found:")
    elements = page.locator('div, li, button, span').all()
    found_accounts = []
    for el in elements:
        try:
            t = el.inner_text().strip()
            if "SAMVREEDDHI" in t or "BLR" in t or "MUM" in t or "HYD" in t:
                if t not in found_accounts and len(t) < 60:
                    found_accounts.append(t)
                    print(f"  * {t}")
        except Exception:
            pass

    # 3. Test changing page size or scraping table
    print("\n3. Testing table extraction...")
    # Change page size to maximum if possible (e.g. 50 or 100)
    page_size_btn = page.locator('[data-testid="page-size-label"], button:has-text("rows")').first
    if page_size_btn.is_visible():
        page_size_btn.click()
        time.sleep(1)
        # Select highest option (e.g. 50 or 100 rows)
        highest = page.locator('li:has-text("50"), li:has-text("100"), [role="option"]:last-child').last
        if highest.is_visible():
            highest.click()
            time.sleep(2)
            print("Changed page size to maximum!")

    time.sleep(3)
    context.close()
