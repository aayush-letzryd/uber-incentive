"""Extract all org testids and exact UUIDs from the switcher."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "uber_chrome_profile"
COOKIES_F   = Path(__file__).parent / "cookies.json"

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
    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
    time.sleep(4)

    # Open User Menu
    user_btn = page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
    user_btn.click()
    time.sleep(1.5)

    # Click Switch account
    page.locator('text="Switch account"').first.click()
    time.sleep(2)

    # Dump all elements with data-testid starting with org-select-
    all_orgs = page.evaluate("""() => {
        const elements = Array.from(document.querySelectorAll('[data-testid^="org-select-"]'));
        return elements.map(el => {
            const testid = el.getAttribute('data-testid');
            const uuid = testid.replace('org-select-', '');
            const text = (el.innerText || '').trim();
            const isRadio = el.querySelectorAll('circle, svg, input[type="radio"]').length > 0 || el.getAttribute('role') === 'radio';
            return { testid, uuid, text, isRadio };
        });
    }""")

    print("\n" + "=" * 70)
    print("ALL DISCOVERED UBER FLEET ORG TESTIDS & UUIDS:")
    print("=" * 70)
    seen = set()
    for o in all_orgs:
        key = (o['uuid'], o['text'])
        if key not in seen and o['text']:
            seen.add(key)
            print(f"UUID: {o['uuid']} | Text: {repr(o['text'])} | isRadio: {o['isRadio']}")

    context.close()
