"""Inspect pagination footer and check total vehicles count across all pages."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path

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

    # Inspect all buttons at the bottom of the page
    print("=== PAGINATION BUTTONS & FOOTER ===")
    footer_text = page.locator('main').inner_text()
    
    # Check page size dropdown options
    page_size_btn = page.locator('[data-testid="page-size-label"], button:has-text("rows")').first
    if page_size_btn.is_visible():
        print(f"Page size button current text: '{page_size_btn.inner_text()}'")
        page_size_btn.click()
        time.sleep(1)
        options = page.locator('li, [role="option"]').all()
        print("Page size options available:")
        for opt in options:
            try:
                print(f"  - {opt.inner_text().strip()}")
            except Exception:
                pass
        page.keyboard.press("Escape")

    # Inspect Next / Prev / Number buttons
    pagination_elements = page.locator('nav button, [data-testid*="page"], [data-testid*="next"], [data-testid*="prev"], button:has-text("Next")').all()
    print(f"\nPagination elements found ({len(pagination_elements)}):")
    for btn in pagination_elements:
        try:
            txt = btn.inner_text().strip()
            testid = btn.get_attribute("data-testid") or ""
            dis = btn.is_disabled()
            cls = btn.get_attribute("class") or ""
            print(f"  Button: text='{txt}' testid='{testid}' disabled={dis} class='{cls[:30]}'")
        except Exception:
            pass

    # Total vehicle count indicator on screen
    print("\nLooking for total count indicators (e.g. 1-50 of 250):")
    for el in page.locator('div, span, p').all():
        try:
            t = el.inner_text().strip()
            if " of " in t and any(c.isdigit() for c in t) and len(t) < 40:
                print(f"  Count Indicator: '{t}'")
        except Exception:
            pass

    time.sleep(2)
    context.close()
