"""Inspect the exact DOM hierarchy of the Uber account switcher drawer."""
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
    # Go to Bangalore promotions first
    page.goto("https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions", timeout=45000)
    time.sleep(4)

    # Open User Menu
    user_btn = page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
    user_btn.click()
    time.sleep(1.5)

    # Click Switch account
    page.locator('text="Switch account"').first.click()
    time.sleep(2)

    # Dump the complete HTML / DOM of the switcher drawer
    dom_dump = page.evaluate("""() => {
        // Find the modal / drawer element
        const modal = document.querySelector('[role="dialog"], [role="menu"], [class*="drawer"], [class*="switcher"], [class*="popover"], [data-baseweb="drawer"], [data-baseweb="popover"]') || document.body;
        
        // Find all clickable / interactive elements in the drawer
        const elements = Array.from(modal.querySelectorAll('*'));
        const results = [];
        for (let el of elements) {
            const text = (el.innerText || '').trim();
            if (text.includes('HYD') || text.includes('MUM') || text.includes('BLR') || text.includes('Samvreeddhi') || text.includes('SAMVREEDDHI')) {
                results.push({
                    tagName: el.tagName,
                    role: el.getAttribute('role'),
                    ariaExpanded: el.getAttribute('aria-expanded'),
                    ariaChecked: el.getAttribute('aria-checked'),
                    className: el.className,
                    dataTestId: el.getAttribute('data-testid'),
                    text: text.slice(0, 100),
                    childCount: el.children.length,
                    hasSvg: el.querySelectorAll('svg').length > 0,
                    hasRadio: el.querySelectorAll('[role="radio"], input[type="radio"], circle').length > 0
                });
            }
        }
        return results;
    }""")

    print(f"Found {len(dom_dump)} matching DOM elements in switcher:")
    for i, item in enumerate(dom_dump[:30]):
        print(f"[{i}] <{item['tagName']}> role='{item['role']}' expanded='{item['ariaExpanded']}' checked='{item['ariaChecked']}' hasSvg={item['hasSvg']} hasRadio={item['hasRadio']} testid='{item['dataTestId']}':")
        print(f"     text: {repr(item['text'][:60])}")

    page.screenshot(path=str(SS_DIR / "debug_switcher_dom.png"))
    context.close()
