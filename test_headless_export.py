import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BASE = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
COOKIES_F = BASE / "cookies.json"
STATE_F = BASE / "storage_state.json"
SS_DIR = BASE / "screenshots"
SS_DIR.mkdir(exist_ok=True)

with sync_playwright() as pw:
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": True,
        "viewport": {"width": 1440, "height": 900},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled"
        ]
    }

    context = pw.chromium.launch_persistent_context(**launch_kwargs)
    page = context.pages[0] if context.pages else context.new_page()
    Stealth().apply_stealth_sync(page)

    if COOKIES_F.exists():
        cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
        context.add_cookies(cookies)

    url = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions"
    print(f"Navigating in headless mode to {url}...")
    page.goto(url, timeout=45000)
    time.sleep(6)

    print(f"Current Page URL: {page.url}")
    print(f"Page Title: {page.title()}")

    ss_path = SS_DIR / "headless_test.png"
    page.screenshot(path=str(ss_path))
    print(f"Saved screenshot: {ss_path}")

    btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if btn.is_visible(timeout=10000):
        print("✅ Export button is VISIBLE in headless mode!")
    else:
        print("❌ Export button NOT visible in headless mode.")

    context.close()
