"""Inspect user menu and org switcher options."""
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

    # 1. Test Export button download
    print("Testing Export button...")
    exp = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    if exp.is_visible():
        try:
            with page.expect_download(timeout=15000) as dl_info:
                exp.click()
            dl = dl_info.value
            out_path = Path(__file__).parent / "uber_reports" / dl.suggested_filename
            dl.save_as(str(out_path))
            print(f"Export downloaded successfully: {out_path} ({out_path.stat().st_size} bytes)")
        except Exception as e:
            print(f"Export download note: {e}")

    # 2. Test clicking user menu button
    print("\nClicking user menu button...")
    user_btn = page.locator('[data-testid="user-menu-button"]').first
    if user_btn.is_visible():
        user_btn.click()
        time.sleep(2)
        page.screenshot(path=str(SS_DIR / "user_menu_open.png"))
        print("Screenshot saved: user_menu_open.png")

        # Check menu items
        items = page.locator('[role="menu"] *, [role="listbox"] *, ul *, div[data-testid*="menu"] *').all()
        print("Menu items visible:")
        for item in items[:25]:
            try:
                t = item.inner_text().strip()
                if t and len(t) < 80:
                    print(f"  - {t}")
            except Exception:
                pass

    # 3. Test clicking the top-left org name
    print("\nClicking top-left org name...")
    org_btn = page.locator('header div:has-text("SAMVREEDDHI"), header button:has-text("SAMVREEDDHI")').first
    if org_btn.is_visible():
        org_btn.click()
        time.sleep(2)
        page.screenshot(path=str(SS_DIR / "org_menu_open.png"))
        print("Screenshot saved: org_menu_open.png")

    time.sleep(3)
    context.close()
