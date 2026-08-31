"""Diagnostic: check exact network calls and download events on Export click."""
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

    # Capture all network requests/responses
    def on_request(req):
        if any(w in req.url.lower() for w in ["export", "promotion", "download", "graphql", "report"]):
            print(f"[REQ] {req.method} {req.url[:110]}")
            if req.post_data:
                print(f"      Payload: {req.post_data[:120]}")

    def on_response(res):
        if any(w in res.url.lower() for w in ["export", "promotion", "download", "graphql", "report"]):
            print(f"[RES] {res.status} {res.url[:110]}")

    page.on("request", on_request)
    page.on("response", on_response)

    # Listen on downloads across context and pages
    def handle_dl(dl):
        print(f"\n🔥🔥 DOWNLOAD EVENT TRIGGERED! 🔥🔥")
        print(f"File: {dl.suggested_filename}")
        print(f"URL: {dl.url}")
        dest = Path(__file__).parent / "uber_reports" / dl.suggested_filename
        dl.save_as(str(dest))
        print(f"Saved to: {dest}")

    page.on("download", handle_dl)
    context.on("page", lambda p: p.on("download", handle_dl))

    print("Opening Mumbai promotions...")
    # Open Mumbai org promotions
    page.goto("https://supplier.uber.com/orgs/44cb587c-a690-44b5-94c2-37539500c7d5/promotions", timeout=45000)
    time.sleep(5)

    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if exp_btn.is_visible():
        print("Clicking Export button...")
        exp_btn.click()
        print("Clicked Export. Monitoring network traffic and download events for 90 seconds...")
        for i in range(18):
            time.sleep(5)
            print(f"  ... waited {(i+1)*5}s")

    time.sleep(3)
    context.close()
