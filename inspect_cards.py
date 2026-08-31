"""Inspect vehicle card container structure."""
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

    # Find elements containing '₹' and inspect their parent rows
    elements = page.locator('text="₹"').all()
    print(f"Elements containing ₹: {len(elements)}")

    cards = page.locator('div:has-text("days remaining"), div:has-text("days")').all()
    print(f"Elements containing 'days': {len(cards)}")

    # Let's inspect the first card's DOM hierarchy
    if elements:
        parent_row = elements[0].evaluate("""el => {
            let cur = el;
            while (cur && cur.parentElement && cur.parentElement.tagName !== 'MAIN' && cur.parentElement.tagName !== 'BODY') {
                if (cur.innerText.includes('Wagon R') || cur.innerText.includes('KA') || cur.innerText.includes('MH') || cur.innerText.includes('AP') || cur.innerText.includes('TS')) {
                    return {
                        tag: cur.tagName,
                        className: cur.className,
                        text: cur.innerText
                    };
                }
                cur = cur.parentElement;
            }
            return null;
        }""")
        print(f"\nMatched Parent Row Structure: {parent_row}")

    # Let's get all top-level rows inside the vehicle list container
    list_data = page.evaluate("""() => {
        const rows = [];
        // Find elements with vehicle plate pattern or ₹
        const allDivs = Array.from(document.querySelectorAll('div, li, [role="listitem"]'));
        for (const el of allDivs) {
            // Check if this element directly contains a vehicle row pattern
            const t = el.innerText || '';
            if (t.includes('₹') && (t.includes('days') || t.includes('day')) && (t.includes('Current') || t.includes('AR'))) {
                // Ensure it's not a huge container containing multiple rows
                const childMatches = Array.from(el.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('₹') && d.innerText.includes('days'));
                if (childMatches.length === 0) {
                    rows.push(t);
                }
            }
        }
        return rows;
    }""")

    print(f"\nTotal vehicle rows extracted via JS: {len(list_data)}")
    for i, row in enumerate(list_data[:5]):
        print(f"  [Vehicle {i+1}]: {repr(row)}")

    time.sleep(2)
    context.close()
