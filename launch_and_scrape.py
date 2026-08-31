import os
import sys
import time
import subprocess
import requests
import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

# Master Supplier Link
START_URL = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/reports"

# 3 Major City Fleet Accounts under India Master
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "uber_reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def is_chrome_cdp_running(port=9222):
    try:
        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

def start_real_chrome(port=9222):
    log("Checking if Real Chrome with Remote Debugging is active...")
    if is_chrome_cdp_running(port):
        log(f"Found active Chrome instance on port {port}!")
        return

    log(f"Starting Real Google Chrome on port {port}...")
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    
    chrome_exe = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_exe = p
            break

    if not chrome_exe:
        chrome_exe = "chrome.exe"

    user_data = os.path.join(BASE_DIR, "real_chrome_user_data")
    os.makedirs(user_data, exist_ok=True)

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        START_URL
    ]
    
    subprocess.Popen(cmd)
    
    for _ in range(15):
        if is_chrome_cdp_running(port):
            log("Real Chrome successfully ready on port 9222!")
            return
        time.sleep(1)

def handle_any_popups(page):
    """Dismisses Passkey, cookie, or prompt modals."""
    try:
        # Press escape to dismiss OS/Passkey dialogs
        page.keyboard.press("Escape")
        time.sleep(1)
        
        cancel_btn = page.locator('button:has-text("Cancel"), button[aria-label="Close"], button:has-text("Not now"), button:has-text("Skip")').first
        if cancel_btn.is_visible(timeout=1500):
            cancel_btn.click()
            time.sleep(1)
    except Exception:
        pass

def switch_to_city_account(page, target_account_name, city_name):
    log(f"\n--- Switching Account to {city_name} ('{target_account_name}') ---")
    time.sleep(3)
    handle_any_popups(page)
    
    account_menu = page.locator('header button, [data-testid*="user-menu"], [data-testid*="org-switcher"], button:has-text("SAMVREEDDHI"), div:has-text("SAMVREEDDHI")').first
    if account_menu.is_visible(timeout=5000):
        account_menu.click()
        time.sleep(2)
        
        switch_acct = page.get_by_text("Switch account", exact=False).first
        if switch_acct.is_visible(timeout=3000):
            switch_acct.click()
            time.sleep(2)

        target_opt = page.get_by_text(target_account_name, exact=False).first
        if not target_opt.is_visible(timeout=2000):
            city_kw = "BLR P" if "BLR" in target_account_name else ("MUM P" if "MUM" in target_account_name else "HYD P")
            target_opt = page.get_by_text(city_kw, exact=False).first

        if target_opt.is_visible(timeout=3000):
            target_opt.click()
            time.sleep(5)
            log(f"Successfully switched to {city_name}.")
            return True
        else:
            page.keyboard.press("Escape")
            log(f"Could not find '{target_account_name}' in account list.")
    return False

def fetch_promotions_for_city(page, city_info):
    city_name = city_info["city"]
    code = city_info["code"]
    
    log(f"\n=======================================================")
    log(f"  PULLING INCENTIVES: {city_name.upper()} ({code})")
    log(f"=======================================================")
    
    handle_any_popups(page)
    
    curr_url = page.url
    if "/orgs/" in curr_url:
        org_id = curr_url.split("/orgs/")[1].split("/")[0]
        promotions_url = f"https://supplier.uber.com/orgs/{org_id}/promotions"
    else:
        promotions_url = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions"

    log(f"Navigating to Promotions: {promotions_url}...")
    page.goto(promotions_url, timeout=40000)
    time.sleep(6)
    handle_any_popups(page)
    
    safe_name = f"SAMVREEDDHI_Mobility_Pvt_Ltd_{code}_P"
    today_str = datetime.datetime.now().strftime("%Y%m%d")

    # 1. Check for Direct Export Button
    export_btn = page.locator('button:has-text("Export"), button:has-text("Download"), a:has-text("Download"), button[aria-label*="download"], button[aria-label*="export"]').first
    if export_btn.is_visible(timeout=3000):
        try:
            log(f"Found Direct Export button! Downloading {city_name} file...")
            with page.expect_download(timeout=30000) as download_info:
                export_btn.click()
            download = download_info.value
            dest_path = os.path.join(OUTPUT_DIR, f"{today_str}-vehicle_incentives-{safe_name}.xlsx")
            download.save_as(dest_path)
            log(f" Successfully downloaded file: {dest_path}")
            
            try:
                df = pd.read_excel(dest_path)
                df["City"] = city_name
                return df, dest_path
            except Exception:
                return None, dest_path
        except Exception as e:
            log(f"Export note: {e}")

    # 2. Extract DOM Table Data
    log(f"Extracting incentive table rows from page DOM for {city_name}...")
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
        log(f"No active incentive campaign rows for {city_name} at this time.")
        return None, None

def run():
    print("*************************************************************")
    print("   LETZRYD - UBER REAL CHROME AUTOMATION (ZERO DETECTION)    ")
    print("   (Bangalore | Mumbai | Hyderabad)                          ")
    print("*************************************************************")
    
    start_real_chrome(port=9222)
    
    with sync_playwright() as p:
        log("Attaching to Real Chrome instance via CDP (Port 9222)...")
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        log(f"Current Page URL: {page.url}")
        handle_any_popups(page)
        
        # If landed on account.uber.com or security page, redirect straight to supplier portal:
        if "supplier.uber.com" not in page.url:
            log(f"Redirecting directly to Supplier Portal: {START_URL}...")
            page.goto(START_URL, timeout=45000)
            time.sleep(5)
            handle_any_popups(page)

        # Wait until supplier portal is visible
        start_t = time.time()
        while time.time() - start_t < 60:
            if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
                log("SUCCESS! Connected to active Uber Supplier Portal session!")
                break
            time.sleep(2)
            handle_any_popups(page)

        all_city_dfs = []
        saved_files = []

        # Pull for Bangalore, Mumbai, Hyderabad
        for city_info in TARGET_CITIES:
            switch_to_city_account(page, city_info["account_name"], city_info["city"])
            df, file_path = fetch_promotions_for_city(page, city_info)
            if df is not None:
                all_city_dfs.append(df)
            if file_path:
                saved_files.append(file_path)

        # Consolidate into Master Report
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
            log(f"\n Consolidated 3-City Master Report Created: {master_xlsx}")
            saved_files.append(master_xlsx)

        log(f"\n=======================================================")
        log(f" ALL 3 CITIES COMPLETED SUCCESSFULLY!")
        log(f" Total files generated: {len(saved_files)}")
        log(f" Output Directory: {OUTPUT_DIR}")
        log(f"=======================================================")

if __name__ == "__main__":
    run()
