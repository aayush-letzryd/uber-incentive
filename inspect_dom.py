"""Quick DOM inspector — loads the portal and dumps buttons/nav elements to identify account switcher."""
import sys, io, time
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"
SS_DIR      = Path(__file__).parent / "screenshots"
import json

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
        print(f"Loaded {len(cookies)} cookies")

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)

    # Wait until truly on supplier portal (not auth)
    print("Waiting for portal to fully load...")
    for _ in range(30):
        if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url and "state=" not in page.url:
            break
        time.sleep(2)
    
    print(f"URL: {page.url}")
    time.sleep(3)  # Let React render
    page.screenshot(path=str(SS_DIR / "portal_loaded.png"))
    print("Screenshot saved: portal_loaded.png")

    # Dump all buttons in the header/nav
    print("\n=== ALL BUTTONS ===")
    buttons = page.locator("button").all()
    for i, btn in enumerate(buttons[:30]):
        try:
            txt = btn.inner_text().strip()[:60]
            attr = btn.get_attribute("data-testid") or btn.get_attribute("aria-label") or ""
            print(f"  [{i}] text='{txt}' testid='{attr}'")
        except Exception:
            pass

    # Dump nav/header links
    print("\n=== HEADER/NAV ELEMENTS ===")
    navs = page.locator("header *, nav *").all()
    for el in navs[:20]:
        try:
            tag = el.evaluate("el => el.tagName")
            txt = el.inner_text().strip()[:60]
            if txt:
                print(f"  <{tag}> '{txt}'")
        except Exception:
            pass

    print("\nDone. Check portal_loaded.png screenshot.")
    time.sleep(5)
    context.close()
