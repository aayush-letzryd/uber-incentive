"""Test direct navigation to Hyderabad promotions page using discovered Org UUID."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"
SS_DIR      = Path(__file__).parent / "screenshots"

HYD_UUID = "f7d7968b-43fe-4c15-bfc8-30a82c8ad5b9"
HYD_URL  = f"https://supplier.uber.com/orgs/{HYD_UUID}/promotions"

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled", "--disable-infobars"],
    )

    if COOKIES_F.exists():
        cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
        context.add_cookies(cookies)

    page = context.pages[0] if context.pages else context.new_page()
    print(f"[*] Navigating directly to Hyderabad URL: {HYD_URL}")
    page.goto(HYD_URL, timeout=45000)
    time.sleep(5)

    print(f"[*] Current Page URL: {page.url}")
    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if exp_btn.is_visible(timeout=5000):
        print(f"✅ SUCCESS: Export button is VISIBLE directly on Hyderabad promotions page!")
        page.screenshot(path=str(SS_DIR / "hyd_direct_promotions.png"))
        print(f"[+] Screenshot saved: screenshots/hyd_direct_promotions.png")
    else:
        print(f"[-] Export button not visible.")

    context.close()
