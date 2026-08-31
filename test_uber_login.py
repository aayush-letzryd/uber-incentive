import os
import sys
import re
import io
import time
import requests
import pandas as pd
from playwright.sync_api import sync_playwright

EMAIL = "uber.india@letzryd.com"
PASSWORD = ""
START_URL = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/reports"
SHEET_ID = "1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "uber_chrome_profile")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def cleanup_chrome_locks():
    """Removes leftover Chrome SingletonLock files from previous interrupted runs."""
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(PROFILE_DIR, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass

def get_otp_from_sheet(initial_date=None, initial_otp=None):
    """Fetches latest OTP from Google Sheet if needed."""
    try:
        res = requests.get(SHEET_CSV_URL, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                for idx in range(min(5, len(df))):
                    msg = str(df.iloc[idx, 0])
                    date_col = str(df.iloc[idx, 2]) if df.shape[1] >= 3 else ""
                    # Match 4-digit code (Uber uses 4 digits) or 6-digit
                    match = re.search(r'\b(\d{4})\b', msg)
                    if match:
                        return match.group(1), date_col, msg
    except Exception as e:
        print(f"Sheet OTP check error: {e}")
    return None, None, ""

def do_login(page):
    print("Checking if already logged in...")
    page.wait_for_timeout(3000)
    current_url = page.url
    if "auth.uber.com" not in current_url and "supplier.uber.com" in current_url:
        print(f"Already on supplier.uber.com ({current_url})! Verifying session...")
        try:
            page.wait_for_selector("nav, header, a[href*='promotions'], a[href*='reports']", timeout=5000)
            print("Session active! Already logged in.")
            return True
        except Exception:
            pass

    print("Initiating login flow...")
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_initial_page.png"))

    # Step 1: Check for email input
    try:
        email_input = page.locator('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS').first
        if email_input.is_visible(timeout=5000):
            print(f"Entering email: {EMAIL}")
            email_input.fill("")
            email_input.type(EMAIL, delay=40)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_email_entered.png"))
            
            # Click Continue
            continue_btn = page.locator('button:has-text("Continue"), button[type="submit"]').first
            if continue_btn.is_visible():
                continue_btn.click()
            else:
                page.keyboard.press("Enter")
            print("Submitted email, waiting for next screen...")
            page.wait_for_timeout(4000)
    except Exception as e:
        print(f"Email entry check: {e}")

    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_after_email_submit.png"))

    # Check if Password field directly visible
    pwd_inputs = page.locator('input[type="password"]')
    if pwd_inputs.count() > 0 and pwd_inputs.first.is_visible():
        print("Password field is directly visible. Entering password...")
        pwd_inputs.first.fill("")
        pwd_inputs.first.type(PASSWORD, delay=40)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_password_entered.png"))
        
        submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
        if submit_btn.is_visible():
            submit_btn.click()
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
    else:
        # Check for 'More options' button/link
        print("Password field not directly visible. Checking for 'More options'...")
        more_opts = page.get_by_text("More options", exact=False).first
        if more_opts.is_visible(timeout=5000):
            print("Clicking 'More options'...")
            more_opts.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_more_options_modal.png"))
            
            # Check for 'See all options' inside modal
            see_all = page.get_by_text("See all options", exact=False).first
            if see_all.is_visible(timeout=3000):
                print("Clicking 'See all options'...")
                see_all.click()
                page.wait_for_timeout(2000)
                page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05b_see_all_options_modal.png"))

            # Click Password option in modal
            print("Looking for 'Password' in More Options...")
            pwd_option = page.get_by_text("Password", exact=True).first
            if not pwd_option.is_visible(timeout=2000):
                pwd_option = page.locator('div[role="dialog"] >> text="Password"').first
                
            if pwd_option.is_visible(timeout=4000):
                print("Found 'Password' option. Clicking...")
                pwd_option.click()
                page.wait_for_timeout(3000)
                page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_after_selecting_password.png"))
                
                # Now find password input
                pwd_input = page.locator('input[type="password"]').first
                if pwd_input.is_visible(timeout=8000):
                    print("Entering password...")
                    pwd_input.fill("")
                    pwd_input.type(PASSWORD, delay=40)
                    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "07_password_entered.png"))
                    
                    submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
                    if submit_btn.is_visible():
                        submit_btn.click()
                    else:
                        page.keyboard.press("Enter")
                    print("Submitted password. Waiting for navigation...")
                    page.wait_for_timeout(8000)
                else:
                    print("Error: Password input not visible after clicking Password option.")
            else:
                print("Could not find 'Password' option inside More Options modal.")
        else:
            print("Could not find 'More options' button.")

    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "08_after_login_attempt.png"))
    print(f"Current URL after login attempt: {page.url}")
    return True

def explore_portal(page):
    print("\n--- Exploring Supplier Portal ---")
    page.wait_for_timeout(4000)
    current_url = page.url
    print(f"Current Portal URL: {current_url}")
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "10_portal_home.png"))

    # Check navbar links
    links = page.locator('nav a, header a, a').all()
    nav_texts = []
    for l in links:
        try:
            txt = l.inner_text().strip()
            href = l.get_attribute("href")
            if txt and href:
                nav_texts.append(f"{txt} -> {href}")
        except Exception:
            pass
    print("Found navigation items:")
    for item in set(nav_texts):
        if any(keyword in item.lower() for keyword in ["report", "promot", "vehic", "driver", "earn", "switch", "samvreeddhi"]):
            print(f"  * {item}")

    # Inspect account switcher / organization switcher
    print("\n--- Inspecting Account Switcher ---")
    account_menu = page.locator('button[aria-label*="account"], button:has-text("SAMVREEDDHI"), div:has-text("SAMVREEDDHI M"), [data-testid*="user-menu"], [data-testid*="org-switcher"]').first
    if account_menu.is_visible(timeout=4000):
        print("Found account dropdown trigger. Clicking...")
        account_menu.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "11_account_menu_open.png"))
        
        # Check for Switch account
        switch_acct = page.get_by_text("Switch account", exact=False).first
        if switch_acct.is_visible(timeout=2000):
            print("Clicking 'Switch account'...")
            switch_acct.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "12_switch_account_list.png"))

    # Navigate directly to Promotions
    print("\n--- Navigating to Promotions Tab ---")
    promotions_link = page.locator('a:has-text("Promotions"), a[href*="promotions"]').first
    if promotions_link.is_visible(timeout=3000):
        promotions_link.click()
    else:
        # construct promotions url
        if "/orgs/" in current_url:
            org_id = current_url.split("/orgs/")[1].split("/")[0]
            page.goto(f"https://supplier.uber.com/orgs/{org_id}/promotions")
        else:
            page.goto("https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/promotions")
            
    page.wait_for_timeout(6000)
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "13_promotions_page.png"))
    print(f"Promotions Page URL: {page.url}")

    # Look for buttons on Promotions page (e.g., Export, Download, Filters)
    promo_buttons = page.locator('button, a[role="button"]').all()
    print("Buttons found on Promotions page:")
    for b in promo_buttons:
        try:
            txt = b.inner_text().strip()
            if txt:
                print(f"  [Button] {txt}")
        except Exception:
            pass

    # Navigate to Reports Tab
    print("\n--- Navigating to Reports Tab ---")
    if "/orgs/" in page.url:
        org_id = page.url.split("/orgs/")[1].split("/")[0]
        page.goto(f"https://supplier.uber.com/orgs/{org_id}/reports")
    else:
        page.goto("https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/reports")

    page.wait_for_timeout(6000)
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "14_reports_page.png"))
    print(f"Reports Page URL: {page.url}")

    # Check Generate Report button
    gen_btn = page.locator('button:has-text("Generate report"), button:has-text("Generate Report"), button:has-text("Create report")').first
    if gen_btn.is_visible(timeout=4000):
        print("Found 'Generate report' button! Clicking to inspect modal...")
        gen_btn.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "15_generate_report_modal.png"))
        
        # Click report type dropdown
        dropdown = page.locator('input[placeholder*="report"], [role="combobox"], [aria-haspopup="listbox"], button:has-text("Driver actioning")').first
        if dropdown.is_visible(timeout=3000):
            dropdown.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "16_report_types_dropdown.png"))
            
            # List all options in dropdown
            options = page.locator('[role="option"], li, [data-testid*="option"]').all()
            print("Report Type Dropdown Options:")
            for opt in options:
                try:
                    txt = opt.inner_text().strip()
                    if txt:
                        print(f"  * {txt}")
                except Exception:
                    pass

def run():
    cleanup_chrome_locks()
    with sync_playwright() as p:
        print("Launching Playwright persistent context (Chrome)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1400, "height": 900},
            accept_downloads=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        print(f"Navigating to {START_URL}...")
        try:
            page.goto(START_URL, timeout=45000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Navigation note: {e}")

        do_login(page)
        
        # Check if login succeeded
        for _ in range(10):
            if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
                print(f"Successfully logged in: {page.url}")
                break
            page.wait_for_timeout(2000)

        if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
            explore_portal(page)
        else:
            print(f"Could not land on supplier portal yet. Current URL: {page.url}")

        print("Finished test step. Keeping browser open for 5 seconds...")
        time.sleep(5)
        context.close()

if __name__ == "__main__":
    run()
