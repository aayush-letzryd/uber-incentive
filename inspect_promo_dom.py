"""Inspect vehicle row selectors and export button."""
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

    # 1. Close blue banner if present
    print("Checking for top banner close button...")
    for sel in ['header button', 'svg[data-baseweb="icon"]', 'div[class*="banner"] button', 'button[aria-label="Close"]']:
        try:
            close_btn = page.locator(sel).first
            if close_btn.is_visible():
                close_btn.click()
                print(f"Closed banner with {sel}")
                time.sleep(1)
                break
        except Exception:
            pass

    # 2. Inspect all div elements with vehicle numbers (e.g. KA51, MH, AP, TS)
    print("\nInspecting vehicle row elements in DOM:")
    cards = page.locator('div:has-text("Maruti"), div:has-text("₹0 /"), div:has-text("4 days")').all()
    print(f"Found {len(cards)} card match elements")
    
    # Check parent containers of vehicle list
    list_items = page.locator('main div[role="row"], div[data-testid*="row"], div[data-testid*="item"]').all()
    print(f"Role row elements: {len(list_items)}")

    # Let's inspect the first 5 children in the promotion list area
    containers = page.locator('main > div, main div').all()
    for c in containers[:15]:
        try:
            t = c.inner_text().strip()
            if "KA51" in t or "Wagon R" in t or "Earnings" in t:
                tag = c.evaluate("el => el.tagName")
                cls = c.evaluate("el => el.className")
                print(f"  Container <{tag}> class='{cls[:50]}':\n    '{t[:100]}'")
        except Exception:
            pass

    # 3. Test force-clicking Export button with JavaScript or dispatchEvent
    print("\nTesting JS click on Export button...")
    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if exp_btn.is_visible():
        page.on("download", lambda dl: print(f"DOWNLOAD CAUGHT: {dl.suggested_filename}"))
        try:
            with page.expect_download(timeout=20000) as dl_info:
                exp_btn.evaluate("btn => btn.click()")
            dl = dl_info.value
            out = Path(__file__).parent / "uber_reports" / dl.suggested_filename
            dl.save_as(str(out))
            print(f"SUCCESS! Downloaded file: {out} ({out.stat().st_size} bytes)")
        except Exception as e:
            print(f"JS Click download result: {e}")

    time.sleep(4)
    context.close()
