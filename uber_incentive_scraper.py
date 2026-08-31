import os
import sys
import re
import io
import time
import random
import datetime
import requests
import pandas as pd
from playwright.sync_api import sync_playwright
from browser_humanizer import (
    launch_humanized_browser,
    apply_stealth_and_fingerprints,
    human_type,
    human_click,
    PROFILE_DIR,
    SCREENSHOTS_DIR
)

EMAIL = "uber.india@letzryd.com"
PASSWORD = ""
START_URL = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/reports"
SHEET_ID = "1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "uber_reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Target Major Accounts
MAJOR_ACCOUNTS = [
    "SAMVREEDDHI MOBILITY India Master",
    "SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P",
    "Samvreeddhi Mobility Pvt. Ltd. MUM P",
    "Samvreeddhi Mobility Pvt Ltd HYD P",
    "ANK Groups Transport",
    "BLR Norther EBS",
    "BLR Norther TBS"
]

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_current_sheet_state():
    try:
        res = requests.get(SHEET_CSV_URL, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                first_msg = str(df.iloc[0, 0])
                first_date = str(df.iloc[0, 2]) if df.shape[1] >= 3 else ""
                match = re.search(r'\b(\d{4})\b', first_msg)
                code = match.group(1) if match else None
                return code, first_date, first_msg
    except Exception as e:
        log(f"Warning: Sheet fetch error: {e}")
    return None, None, ""

def poll_for_new_otp(initial_date, initial_code, timeout_seconds=90):
    log(f"Waiting for new 4-digit Uber OTP in Google Sheet (Timeout: {timeout_seconds}s)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        code, d_str, msg = get_current_sheet_state()
        if code and (code != initial_code or d_str != initial_date):
            log(f"Found new OTP in Google Sheet: {code} (at {d_str})")
            return code
        time.sleep(4)
    return None

def handle_otp_input(page, initial_sheet_date, initial_sheet_code):
    log("SMS 2FA verification screen detected.")
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "otp_screen.png"))
    
    otp = poll_for_new_otp(initial_sheet_date, initial_sheet_code, timeout_seconds=45)
    if not otp:
        otp, _, _ = get_current_sheet_state()

    if otp and len(otp) == 4:
        log(f"Entering 4-digit OTP: {otp}")
        digit_inputs = page.locator('input[type="tel"], input[aria-label*="digit"], input[maxlength="1"]').all()
        if len(digit_inputs) >= 4:
            for idx, digit in enumerate(otp):
                digit_inputs[idx].fill(digit)
                time.sleep(random.uniform(0.1, 0.2))
        else:
            first_input = page.locator('input[type="tel"], input[type="text"]').first
            if first_input.is_visible():
                first_input.click()
                first_input.fill("")
                for digit in otp:
                    page.keyboard.press(digit)
                    time.sleep(random.uniform(0.1, 0.2))

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "otp_entered.png"))
        time.sleep(1)
        
        next_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button[type="submit"]').first
        if next_btn.is_visible():
            human_click(page, next_btn)
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

def ensure_login(page):
    log("Checking current authentication state...")
    page.wait_for_timeout(3000)
    current_url = page.url
    
    if "supplier.uber.com" in current_url and "auth.uber.com" not in current_url:
        log(f"Already authenticated on Supplier Portal: {current_url}")
        return True

    init_code, init_date, _ = get_current_sheet_state()
    log(f"Initial Sheet OTP baseline: {init_code} (at {init_date})")

    # Email Step
    try:
        email_input = page.locator('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS').first
        if email_input.is_visible(timeout=5000):
            log(f"Entering email: {EMAIL}")
            human_type(email_input, EMAIL)
            time.sleep(0.4)
            continue_btn = page.locator('button:has-text("Continue"), button[type="submit"]').first
            if continue_btn.is_visible():
                human_click(page, continue_btn)
            else:
                page.keyboard.press("Enter")
            page.wait_for_timeout(3500)
    except Exception as e:
        log(f"Email entry check: {e}")

    # Password First
    pwd_inputs = page.locator('input[type="password"]')
    if pwd_inputs.count() > 0 and pwd_inputs.first.is_visible():
        log("Password input directly visible. Entering password...")
        human_type(pwd_inputs.first, PASSWORD)
        time.sleep(0.4)
        submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
        if submit_btn.is_visible():
            human_click(page, submit_btn)
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(5000)
    else:
        # Check for More options -> See all options -> Password
        more_opts = page.get_by_text("More options", exact=False).first
        if more_opts.is_visible(timeout=4000):
            log("Clicking 'More options'...")
            human_click(page, more_opts)
            page.wait_for_timeout(1800)
            
            see_all = page.get_by_text("See all options", exact=False).first
            if see_all.is_visible(timeout=2000):
                log("Clicking 'See all options'...")
                human_click(page, see_all)
                page.wait_for_timeout(1800)

            pwd_option = page.get_by_text("Password", exact=True).first
            if not pwd_option.is_visible(timeout=2000):
                pwd_option = page.locator('div[role="dialog"] >> text="Password"').first

            if pwd_option.is_visible(timeout=3000):
                log("Selecting 'Password' option...")
                human_click(page, pwd_option)
                page.wait_for_timeout(2500)
                
                pwd_input = page.locator('input[type="password"]').first
                if pwd_input.is_visible(timeout=5000):
                    log("Entering password...")
                    human_type(pwd_input, PASSWORD)
                    time.sleep(0.4)
                    submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
                    if submit_btn.is_visible():
                        human_click(page, submit_btn)
                    else:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(6000)

    # 2FA Check if needed
    if "code sent via SMS" in page.content() or page.locator('input[type="tel"]').count() > 0:
        handle_otp_input(page, init_date, init_code)

    # Verify Supplier Portal
    for _ in range(12):
        if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
            log(f"Login successful! Landed on: {page.url}")
            page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "login_success.png"))
            return True
        page.wait_for_timeout(2000)

    log(f"Auth finished. Current URL: {page.url}")
    return "supplier.uber.com" in page.url and "auth.uber.com" not in page.url

def get_available_accounts(page):
    log("Discovering available organizations/accounts...")
    accounts = []
    account_menu = page.locator('header button, [data-testid*="user-menu"], [data-testid*="org-switcher"], button:has-text("SAMVREEDDHI"), div:has-text("SAMVREEDDHI")').first
    if account_menu.is_visible(timeout=4000):
        human_click(page, account_menu)
        page.wait_for_timeout(2000)
        
        switch_acct = page.get_by_text("Switch account", exact=False).first
        if switch_acct.is_visible(timeout=2000):
            human_click(page, switch_acct)
            page.wait_for_timeout(2000)
            
        items = page.locator('li, [role="menuitem"], [role="option"], div[role="button"]').all()
        for it in items:
            try:
                name = it.inner_text().strip()
                if name and not any(skip in name.lower() for skip in ["switch account", "log out", "sign out", "help", "back"]):
                    clean_name = name.split("\n")[0].strip()
                    if clean_name and clean_name not in accounts:
                        accounts.append(clean_name)
            except Exception:
                pass
                
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

    log(f"Discovered accounts: {accounts}")
    return accounts

def switch_to_account(page, target_account_name):
    log(f"Switching account to: {target_account_name}...")
    account_menu = page.locator('header button, [data-testid*="user-menu"], [data-testid*="org-switcher"], button:has-text("SAMVREEDDHI"), div:has-text("SAMVREEDDHI")').first
    if account_menu.is_visible(timeout=4000):
        human_click(page, account_menu)
        page.wait_for_timeout(1500)
        
        switch_acct = page.get_by_text("Switch account", exact=False).first
        if switch_acct.is_visible(timeout=2000):
            human_click(page, switch_acct)
            page.wait_for_timeout(1500)

        target_opt = page.get_by_text(target_account_name, exact=False).first
        if target_opt.is_visible(timeout=3000):
            human_click(page, target_opt)
            page.wait_for_timeout(4000)
            log(f"Successfully switched to {target_account_name}. URL: {page.url}")
            return True
        else:
            page.keyboard.press("Escape")
    return False

def fetch_promotions_for_account(page, account_name):
    log(f"\n--- Extracting Vehicle Incentives for: {account_name} ---")
    curr_url = page.url
    if "/orgs/" in curr_url:
        org_id = curr_url.split("/orgs/")[1].split("/")[0]
        promotions_url = f"https://supplier.uber.com/orgs/{org_id}/promotions"
    else:
        promotions_url = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/promotions"

    log(f"Navigating to {promotions_url}...")
    page.goto(promotions_url, timeout=30000)
    page.wait_for_timeout(5000)
    
    safe_name = account_name.replace(" ", "_").replace(".", "").replace("/", "_")
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, f"promotions_{safe_name}.png"))

    # Check for Export button
    export_btn = page.locator('button:has-text("Export"), button:has-text("Download"), a:has-text("Download"), button[aria-label*="download"], button[aria-label*="export"]').first
    if export_btn.is_visible(timeout=3000):
        log(f"Found Export button for {account_name}! Downloading...")
        try:
            with page.expect_download(timeout=30000) as download_info:
                human_click(page, export_btn)
            download = download_info.value
            dest_path = os.path.join(OUTPUT_DIR, f"vehicle_incentives_{safe_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            download.save_as(dest_path)
            log(f"Downloaded incentive file to: {dest_path}")
            return dest_path
        except Exception as e:
            log(f"Download trigger note: {e}")

    # DOM Table Scraper fallback
    log(f"Extracting incentive table rows for {account_name} from page...")
    rows = page.locator('table tbody tr, [role="row"]').all()
    table_data = []
    for r in rows:
        try:
            cols = r.locator('td, [role="cell"]').all()
            if cols:
                row_vals = [c.inner_text().strip() for c in cols]
                table_data.append(row_vals)
        except Exception:
            pass

    if table_data:
        # Standardize expected columns
        standard_cols = [
            "Vehicle name", "Number plate", "Start date", "End date",
            "Acceptance rate", "Target acceptance rate", "Trips completed",
            "Trip target", "Total payout", "Status", "Driver trip count breakdown"
        ]
        df = pd.DataFrame(table_data)
        if len(df.columns) == len(standard_cols):
            df.columns = standard_cols
            
        csv_path = os.path.join(OUTPUT_DIR, f"vehicle_incentives_{safe_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        df.to_csv(csv_path, index=False)
        log(f"Saved {len(df)} records to: {csv_path}")
        return csv_path
    else:
        log(f"No active incentive campaigns or empty records for {account_name}.")
        return None

def run():
    with sync_playwright() as p:
        log("Launching Humanized Chrome Browser with Anti-Detection Evasions...")
        context = launch_humanized_browser(p)
        page = context.pages[0] if context.pages else context.new_page()
        apply_stealth_and_fingerprints(page)
        
        log(f"Navigating to {START_URL}...")
        try:
            page.goto(START_URL, timeout=45000)
        except Exception as e:
            log(f"Initial navigation notice: {e}")

        if not ensure_login(page):
            log("Authentication pending. Please review browser window or screenshots.")
            time.sleep(10)
            return

        log("Access verified! Proceeding with multi-account incentive collection...")
        discovered_accounts = get_available_accounts(page)
        target_accounts = [acc for acc in MAJOR_ACCOUNTS if any(sub in acc.lower() for sub in ["master", "blr", "mum", "hyd", "norther"])] or MAJOR_ACCOUNTS
        
        results = []
        for acct in target_accounts:
            switched = switch_to_account(page, acct)
            time.sleep(2)
            res = fetch_promotions_for_account(page, acct)
            if res:
                results.append(res)
                
        log(f"\n=======================================================")
        log(f"Finished! Total files generated/downloaded: {len(results)}")
        log(f"Directory: {OUTPUT_DIR}")
        log(f"=======================================================")
        
        time.sleep(5)
        context.close()

if __name__ == "__main__":
    run()
