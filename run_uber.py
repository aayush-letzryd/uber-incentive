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
from cookie_manager import save_session_state, load_session_cookies, STATE_FILE

EMAIL = "uber.india@letzryd.com"
PASSWORD = "Letzuberp123"
START_URL = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/reports"
SHEET_ID = "1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "uber_reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# The 3 Major City Fleet Accounts to pull
TARGET_CITIES = [
    {
        "city": "Bangalore",
        "account_name": "SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P",
        "code": "BLR"
    },
    {
        "city": "Mumbai",
        "account_name": "Samvreeddhi Mobility Pvt. Ltd. MUM P",
        "code": "MUM"
    },
    {
        "city": "Hyderabad",
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "code": "HYD"
    }
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
        log(f"Sheet fetch note: {e}")
    return None, None, ""

def poll_for_new_otp(initial_date, initial_code, timeout_seconds=90):
    log(f"Waiting for new Uber OTP in Google Sheet (Timeout: {timeout_seconds}s)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        code, d_str, msg = get_current_sheet_state()
        if code and (code != initial_code or d_str != initial_date):
            log(f"Retrieved new OTP from Google Sheet: {code} (at {d_str})")
            return code
        time.sleep(4)
    return None

def handle_otp_input(page, initial_sheet_date, initial_sheet_code):
    log("2FA verification screen detected.")
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

def ensure_login(page, context):
    log("Checking active session & saved cookies...")
    page.wait_for_timeout(3000)
    current_url = page.url
    
    if "supplier.uber.com" in current_url and "auth.uber.com" not in current_url:
        log(f"Already logged in via saved session! URL: {current_url}")
        save_session_state(context)
        return True

    init_code, init_date, _ = get_current_sheet_state()

    # Enter Email
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
        log(f"Email note: {e}")

    # Password first
    pwd_inputs = page.locator('input[type="password"]')
    if pwd_inputs.count() > 0 and pwd_inputs.first.is_visible():
        log("Entering password...")
        human_type(pwd_inputs.first, PASSWORD)
        time.sleep(0.4)
        submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
        if submit_btn.is_visible():
            human_click(page, submit_btn)
        else:
            page.keyboard.press("Enter")
        page.wait_for_timeout(5000)
    else:
        # More options -> See all options -> Password
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
                log("Selecting 'Password'...")
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

    # 2FA if requested
    if "code sent via SMS" in page.content() or page.locator('input[type="tel"]').count() > 0:
        handle_otp_input(page, init_date, init_code)

    # Confirm landing
    for _ in range(12):
        if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
            log(f"Login successful! Landed on: {page.url}")
            save_session_state(context)
            return True
        page.wait_for_timeout(2000)

    if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
        save_session_state(context)
        return True
    return False

def switch_to_city_account(page, target_account_name, city_name):
    log(f"Switching account to {city_name} ('{target_account_name}')...")
    account_menu = page.locator('header button, [data-testid*="user-menu"], [data-testid*="org-switcher"], button:has-text("SAMVREEDDHI"), div:has-text("SAMVREEDDHI")').first
    if account_menu.is_visible(timeout=4000):
        human_click(page, account_menu)
        page.wait_for_timeout(1500)
        
        switch_acct = page.get_by_text("Switch account", exact=False).first
        if switch_acct.is_visible(timeout=2000):
            human_click(page, switch_acct)
            page.wait_for_timeout(1500)

        # Match account name loosely or by city keyword (BLR, MUM, HYD)
        target_opt = page.get_by_text(target_account_name, exact=False).first
        if not target_opt.is_visible(timeout=2000):
            # Try city abbreviation match
            city_kw = "BLR P" if "BLR" in target_account_name else ("MUM P" if "MUM" in target_account_name else "HYD P")
            target_opt = page.get_by_text(city_kw, exact=False).first

        if target_opt.is_visible(timeout=3000):
            human_click(page, target_opt)
            page.wait_for_timeout(4000)
            log(f"Successfully switched to {city_name}.")
            return True
        else:
            page.keyboard.press("Escape")
            log(f"Warning: Could not locate '{target_account_name}' in account dropdown.")
    return False

def fetch_promotions_for_city(page, city_info):
    city_name = city_info["city"]
    account_name = city_info["account_name"]
    code = city_info["code"]
    
    log(f"\n=======================================================")
    log(f"  PULLING VEHICLE INCENTIVES: {city_name.upper()} ({code})")
    log(f"=======================================================")
    
    curr_url = page.url
    if "/orgs/" in curr_url:
        org_id = curr_url.split("/orgs/")[1].split("/")[0]
        promotions_url = f"https://supplier.uber.com/orgs/{org_id}/promotions"
    else:
        promotions_url = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/promotions"

    page.goto(promotions_url, timeout=30000)
    page.wait_for_timeout(5000)
    
    safe_name = f"SAMVREEDDHI_Mobility_Pvt_Ltd_{code}_P"
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, f"promotions_{code}.png"))

    today_str = datetime.datetime.now().strftime("%Y%m%d")

    # 1. Try Direct Export Button if available on page
    export_btn = page.locator('button:has-text("Export"), button:has-text("Download"), a:has-text("Download"), button[aria-label*="download"], button[aria-label*="export"]').first
    if export_btn.is_visible(timeout=3000):
        try:
            log(f"Direct Export button found for {city_name}! Downloading...")
            with page.expect_download(timeout=30000) as download_info:
                human_click(page, export_btn)
            download = download_info.value
            dest_path = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-{safe_name}.xlsx")
            download.save_as(dest_path)
            log(f" Downloaded incentive file: {dest_path}")
            
            # Read back into dataframe to allow consolidation
            try:
                df = pd.read_excel(dest_path)
                df["City"] = city_name
                return df, dest_path
            except Exception:
                return None, dest_path
        except Exception as e:
            log(f"Direct export download note: {e}")

    # 2. Extract DOM Table Data
    log(f"Extracting incentive table rows for {city_name} from page...")
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
        standard_cols = [
            "Vehicle name", "Number plate", "Start date", "End date",
            "Acceptance rate", "Target acceptance rate", "Trips completed",
            "Trip target", "Total payout", "Status", "Driver trip count breakdown"
        ]
        df = pd.DataFrame(table_data)
        if len(df.columns) == len(standard_cols):
            df.columns = standard_cols
            
        df["City"] = city_name
        
        csv_path = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-{safe_name}.csv")
        xlsx_path = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-{safe_name}.xlsx")
        df.to_csv(csv_path, index=False)
        try:
            df.to_excel(xlsx_path, index=False)
        except Exception:
            pass
        log(f" Generated file with {len(df)} records for {city_name}: {xlsx_path}")
        return df, xlsx_path
    else:
        log(f"No active incentive campaign rows found for {city_name} at this time.")
        return None, None

def main():
    print("*************************************************************")
    print("  LETZRYD - UBER 3 MAJOR CITIES INCENTIVE AUTOMATION         ")
    print("  (Bangalore - Mumbai - Hyderabad)                          ")
    print("*************************************************************")
    
    with sync_playwright() as p:
        context = launch_humanized_browser(p)
        page = context.pages[0] if context.pages else context.new_page()
        apply_stealth_and_fingerprints(page)
        
        load_session_cookies(context)
        
        log(f"Navigating to {START_URL}...")
        try:
            page.goto(START_URL, timeout=45000)
        except Exception as e:
            log(f"Navigation notice: {e}")

        if not ensure_login(page, context):
            log("Authentication could not complete automatically. Please check browser window.")
            time.sleep(10)
            return

        all_city_dfs = []
        saved_files = []

        # Process the 3 major city entities
        for city_info in TARGET_CITIES:
            switched = switch_to_city_account(page, city_info["account_name"], city_info["city"])
            time.sleep(2)
            df, file_path = fetch_promotions_for_city(page, city_info)
            if df is not None:
                all_city_dfs.append(df)
            if file_path:
                saved_files.append(file_path)

        # Consolidate into Master 3-City Combined Report
        if all_city_dfs:
            combined_df = pd.concat(all_city_dfs, ignore_index=True)
            today_str = datetime.datetime.now().strftime("%Y%m%d")
            master_csv = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv")
            master_xlsx = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx")
            combined_df.to_csv(master_csv, index=False)
            try:
                combined_df.to_excel(master_xlsx, index=False)
            except Exception:
                pass
            log(f"\n Created Consolidated Master Report: {master_xlsx} ({len(combined_df)} total records)")
            saved_files.append(master_xlsx)

        save_session_state(context)
        
        log(f"\n=======================================================")
        log(f" ALL 3 CITIES COMPLETED!")
        log(f" Total files generated: {len(saved_files)}")
        log(f" Destination Folder: {OUTPUT_DIR}")
        log(f"=======================================================")
        
        time.sleep(5)
        context.close()

if __name__ == "__main__":
    main()
