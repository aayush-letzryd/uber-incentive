"""Test robust card parser across all pagination pages."""
import sys, io, time, json
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from pathlib import Path
import pandas as pd

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

    # Change to 50/100 rows per page
    try:
        page_size_btn = page.locator('[data-testid="page-size-label"], button:has-text("rows")').first
        if page_size_btn.is_visible():
            page_size_btn.click()
            time.sleep(1)
            highest = page.locator('li:has-text("50"), li:has-text("100"), [role="option"]:last-child').last
            if highest.is_visible():
                highest.click()
                time.sleep(2)
    except Exception:
        pass

    all_pages_records = []
    page_num = 1

    js_extractor = """() => {
        const records = [];
        const allDivs = Array.from(document.querySelectorAll('div, li'));
        for (const el of allDivs) {
            const t = el.innerText || '';
            if (t.includes('₹') && (t.includes('days') || t.includes('day')) && (t.includes('Current') || t.includes('AR') || t.includes('%'))) {
                const childMatches = Array.from(el.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('₹') && d.innerText.includes('days'));
                if (childMatches.length === 0) {
                    const text = t.replace(/\\u00a0/g, ' ').trim();
                    const plateMatch = text.match(/([A-Z]{2}\\s*\\d{1,2}\\s*[A-Z]{1,3}\\s*\\d{1,4})/i);
                    const plate = plateMatch ? plateMatch[1].replace(/\\s+/g, '') : '';
                    
                    let vname = '';
                    if (plate) {
                        const afterPlate = text.substring(text.indexOf(plate) + plate.length);
                        const beforeRupee = afterPlate.split('₹')[0];
                        vname = beforeRupee.trim();
                    }
                    
                    const earnMatch = text.match(/₹\\s*([\\d,]+)\\s*\\/\\s*([\\d,]+)/);
                    const currEarn = earnMatch ? '₹' + earnMatch[1] : '';
                    const targetEarn = earnMatch ? '₹' + earnMatch[2] : '';
                    
                    const tripMatch = text.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
                    const currTrips = tripMatch ? tripMatch[1] : '';
                    const targetTrips = tripMatch ? tripMatch[2] : '';
                    
                    const targetArMatch = text.match(/(\\d+)\\s*%/);
                    const targetAr = targetArMatch ? targetArMatch[1] + '%' : '';
                    const currArMatch = text.match(/Current\\s*(\\d+)\\s*%/i);
                    const currAr = currArMatch ? currArMatch[1] + '%' : '';
                    
                    const daysMatch = text.match(/(\\d+)\\s*days?/i);
                    const days = daysMatch ? daysMatch[0] : '';
                    
                    records.push({
                        "Number plate": plate,
                        "Vehicle name": vname,
                        "Total payout": currEarn,
                        "Target payout": targetEarn,
                        "Trips completed": currTrips,
                        "Trip target": targetTrips,
                        "Target acceptance rate": targetAr,
                        "Acceptance rate": currAr,
                        "Status": "Active",
                        "Days remaining": days
                    });
                }
            }
        }
        return records;
    }"""

    while True:
        records = page.evaluate(js_extractor)
        print(f"Page {page_num}: Extracted {len(records)} vehicle records")
        for r in records:
            if r["Number plate"] and not any(x["Number plate"] == r["Number plate"] for x in all_pages_records):
                all_pages_records.append(r)

        # Next page check
        next_btn = page.locator('[data-testid="next-button"], button[aria-label="Next page"]').first
        if next_btn.is_visible() and not next_btn.is_disabled():
            try:
                next_btn.click()
                time.sleep(2)
                page_num += 1
            except Exception:
                break
        else:
            break

    df = pd.DataFrame(all_pages_records)
    print(f"\n=======================================================")
    print(f"TOTAL EXTRACTED VEHICLES: {len(df)}")
    print(f"=======================================================")
    print(df.head(10).to_string())

    time.sleep(2)
    context.close()
