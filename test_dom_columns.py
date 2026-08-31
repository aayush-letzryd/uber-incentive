"""Test clean child DOM column parsing."""
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

    # Inspect children of first 3 vehicle cards
    js_deep_inspect = """() => {
        const results = [];
        // Find cards
        const allDivs = Array.from(document.querySelectorAll('div'));
        for (const el of allDivs) {
            const t = el.innerText || '';
            if (t.includes('₹') && (t.includes('days') || t.includes('day')) && (t.includes('Current') || t.includes('AR'))) {
                const childMatches = Array.from(el.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('₹') && d.innerText.includes('days'));
                if (childMatches.length === 0) {
                    // This is a single card row
                    // Get all direct children or distinct text blocks
                    const directChildren = Array.from(el.children).map(c => c.innerText.replace(/\\u00a0/g, ' ').trim());
                    results.push({
                        "raw": t,
                        "directChildren": directChildren
                    });
                    if (results.length >= 3) break;
                }
            }
        }
        return results;
    }"""

    cards = page.evaluate(js_deep_inspect)
    for i, c in enumerate(cards):
        print(f"\n=== CARD {i+1} ===")
        print("Direct Children:")
        for j, ch in enumerate(c["directChildren"]):
            print(f"  [{j}]: {repr(ch)}")

    time.sleep(2)
    context.close()
