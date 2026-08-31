import os
import sys
import time
import json
import datetime
import pandas as pd
from google.cloud import storage
from playwright.sync_api import sync_playwright

# GCP Configuration
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "letzryd-uber-reports")
COOKIE_BLOB_NAME = "secrets/uber_storage_state.json"
START_URL = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/reports"

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
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def download_cookies_from_gcs(dest_path="storage_state.json"):
    """Downloads saved authenticated session cookies from Google Cloud Storage."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(COOKIE_BLOB_NAME)
        if blob.exists():
            blob.download_to_filename(dest_path)
            log(f"Restored session state from gs://{GCS_BUCKET_NAME}/{COOKIE_BLOB_NAME}")
            return True
    except Exception as e:
        log(f"Notice: Could not load cookies from GCS ({e}). Using local state.")
    return os.path.exists("storage_state.json")

def upload_file_to_gcs(local_path, gcs_dest_blob):
    """Uploads generated Excel/CSV reports to Google Cloud Storage."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_dest_blob)
        blob.upload_from_filename(local_path)
        log(f" Uploaded to gs://{GCS_BUCKET_NAME}/{gcs_dest_blob}")
    except Exception as e:
        log(f"GCS upload warning: {e}")

def save_cookies_to_gcs(context, local_path="storage_state.json"):
    """Persists updated session cookies back to GCS for the next scheduled run."""
    try:
        context.storage_state(path=local_path)
        upload_file_to_gcs(local_path, COOKIE_BLOB_NAME)
        log("Successfully refreshed session state in GCS!")
    except Exception as e:
        log(f"Cookie save warning: {e}")

def switch_to_city_account(page, target_account_name, city_name):
    log(f"Switching account to {city_name} ('{target_account_name}')...")
    time.sleep(3)
    
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
            log(f"Switched to {city_name}.")
            return True
        else:
            page.keyboard.press("Escape")
    return False

def fetch_promotions_for_city(page, city_info, output_dir="./output"):
    city_name = city_info["city"]
    code = city_info["code"]
    
    log(f"Extracting Vehicle Incentives for {city_name.upper()} ({code})...")
    
    curr_url = page.url
    if "/orgs/" in curr_url:
        org_id = curr_url.split("/orgs/")[1].split("/")[0]
        promotions_url = f"https://supplier.uber.com/orgs/{org_id}/promotions"
    else:
        promotions_url = "https://supplier.uber.com/orgs/ebb10afb-c08b-463e-a4fa-33b64674adfd/promotions"

    page.goto(promotions_url, timeout=40000)
    time.sleep(6)
    
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    safe_name = f"SAMVREEDDHI_Mobility_Pvt_Ltd_{code}_P"
    
    # 1. Direct Export
    export_btn = page.locator('button:has-text("Export"), button:has-text("Download"), a:has-text("Download"), button[aria-label*="download"], button[aria-label*="export"]').first
    if export_btn.is_visible(timeout=3000):
        try:
            with page.expect_download(timeout=30000) as download_info:
                export_btn.click()
            download = download_info.value
            dest_path = os.path.join(output_dir, f"{today_str}-vehicle_incentives-{safe_name}.xlsx")
            download.save_as(dest_path)
            log(f"Direct export downloaded: {dest_path}")
            
            try:
                df = pd.read_excel(dest_path)
                df["City"] = city_name
                return df, dest_path
            except Exception:
                return None, dest_path
        except Exception:
            pass

    # 2. DOM Scraper
    rows = page.locator('table tbody tr, [role="row"]').all()
    table_data = []
    for r in rows:
        try:
            cols = r.locator('td, [role="cell"]').all()
            if cols:
                table_data.append([c.inner_text().strip() for c in cols])
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
        xlsx_path = os.path.join(output_dir, f"{today_str}-vehicle_incentives-{safe_name}.xlsx")
        df.to_excel(xlsx_path, index=False)
        return df, xlsx_path

    return None, None

def run_cloud_job():
    log("Starting Scheduled Uber Incentives Cloud Ingestion Job...")
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Restore cookies from Cloud Storage
    state_file = "storage_state.json"
    download_cookies_from_gcs(state_file)
    
    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        
        # Launch Headless Chrome in Docker
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        storage_kwargs = {"storage_state": state_file} if os.path.exists(state_file) else {}
        context = browser.new_context(
            user_agent=user_agent,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            geolocation={"latitude": 12.9716, "longitude": 77.5946},
            permissions=["geolocation"],
            viewport={"width": 1440, "height": 900},
            **storage_kwargs
        )
        
        page = context.new_page()
        log(f"Navigating to {START_URL}...")
        page.goto(START_URL, timeout=45000)
        time.sleep(5)
        
        if "auth.uber.com" in page.url:
            log("ERROR: Stored session in GCS expired. Please re-run local login once to refresh cookies in GCS.")
            return

        all_city_dfs = []
        saved_files = []
        today_str = datetime.datetime.now().strftime("%Y%m%d")

        for city_info in TARGET_CITIES:
            switch_to_city_account(page, city_info["account_name"], city_info["city"])
            df, file_path = fetch_promotions_for_city(page, city_info, output_dir)
            if df is not None:
                all_city_dfs.append(df)
            if file_path:
                saved_files.append(file_path)
                # Upload individual city file to GCS
                upload_file_to_gcs(file_path, f"vehicle_incentives/{today_str}/{os.path.basename(file_path)}")

        # Consolidated Master Report
        if all_city_dfs:
            combined_df = pd.concat(all_city_dfs, ignore_index=True)
            master_xlsx = os.path.join(output_dir, f"{today_str}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx")
            combined_df.to_excel(master_xlsx, index=False)
            log(f"Created Consolidated 3-City Master Report: {master_xlsx}")
            upload_file_to_gcs(master_xlsx, f"vehicle_incentives/{today_str}/{os.path.basename(master_xlsx)}")

        # Refresh session in GCS
        save_cookies_to_gcs(context, state_file)
        
        log(f"Cloud Execution Finished! {len(saved_files)} city reports processed.")
        browser.close()

if __name__ == "__main__":
    run_cloud_job()
