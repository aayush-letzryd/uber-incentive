"""Check exact total vehicle count and pagination buttons for Bangalore."""
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

    # Dismiss banner
    try:
        page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first.click()
        time.sleep(1)
    except Exception:
        pass

    # Check footer pagination status
    pagination_info = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.innerText.trim(),
            testid: b.getAttribute('data-testid') || '',
            disabled: b.disabled || b.getAttribute('aria-disabled') === 'true'
        }));
        
        // Find text like '1-10 of 200' or similar
        const allText = Array.from(document.querySelectorAll('div, p, span')).map(el => el.innerText.trim()).filter(t => t.includes(' of ') || t.includes('rows') || t.includes('Page'));
        
        return {
            buttons: btns.filter(b => b.testid.includes('page') || b.testid.includes('button') || b.text.includes('Next') || b.text.includes('Prev')),
            textSnippets: Array.from(new Set(allText)).slice(0, 15)
        };
    }""")

    print("Pagination Buttons:")
    for b in pagination_info["buttons"]:
        print(f"  {b}")

    print("\nText Snippets related to count/pages:")
    for t in pagination_info["textSnippets"]:
        print(f"  {t}")

    time.sleep(2)
    context.close()
