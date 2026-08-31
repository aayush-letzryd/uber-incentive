"""
LETZRYD · LOCAL VISUAL RUNNER (PRODUCTION v4.8)
===============================================
- Stable browser lifecycle with popup tab isolation
- Downloads captured via context.on('download')
- Sequential processing of Bangalore, Mumbai, Hyderabad
- Builds Master Consolidated Excel
"""

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import time
import json
import shutil
import datetime
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from playwright_stealth import Stealth

BASE = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
COOKIES_F = BASE / "cookies.json"
OUT_DIR = BASE / "uber_reports"
USER_DL_DIR = Path.home() / "Downloads"

for d in [PROFILE_DIR, OUT_DIR, USER_DL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = [
    {
        "city": "Bangalore",
        "code": "BLR",
        "org_uuid": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "account_name": "SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P",
        "short_name": "BLR P",
        "file_keyword": "BLR_P",
        "max_wait_seconds": 900
    },
    {
        "city": "Mumbai",
        "code": "MUM",
        "org_uuid": "44cb587c-a690-44b5-94c2-37539500c7d5",
        "account_name": "Samvreeddhi Mobility Pvt. Ltd. MUM P",
        "short_name": "MUM P",
        "file_keyword": "MUM_P",
        "max_wait_seconds": 600
    },
    {
        "city": "Hyderabad",
        "code": "HYD",
        "org_uuid": None,
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "short_name": "HYD P",
        "file_keyword": "HYD_P",
        "max_wait_seconds": 600
    }
]


def cleanup_locks():
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass


def ensure_main_page(context: BrowserContext, main_page: Page) -> Page:
    # Safely close any extra popup tabs
    for p in list(context.pages):
        if p != main_page:
            try:
                if not p.is_closed():
                    p.close()
            except Exception:
                pass
    
    if main_page is None or main_page.is_closed():
        pages = [p for p in context.pages if not p.is_closed()]
        if pages:
            main_page = pages[0]
        else:
            main_page = context.new_page()
    
    return main_page


def dismiss_banner(page: Page):
    try:
        if not page.is_closed():
            close_btn = page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first
            if close_btn.is_visible(timeout=1500):
                close_btn.click()
                time.sleep(1)
    except Exception:
        pass


def is_valid_incentive_file(file_path: Path) -> bool:
    try:
        if not file_path.exists() or file_path.stat().st_size < 100:
            return False
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            header = f.readline()
            return "Vehicle name" in header and "Number plate" in header
    except Exception:
        return False


def switch_to_city_visual(context: BrowserContext, main_page: Page, target: dict) -> Page:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    org_uuid = target.get("org_uuid")

    print(f"\n=======================================================")
    print(f"👉 [SWITCHING ACCOUNT] -> {city} ('{short}')")
    print(f"=======================================================")

    # 1. Direct URL navigation
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        print(f"[*] Navigating to {city} URL: {url}")
        try:
            main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)
            main_page = ensure_main_page(context, main_page)
            dismiss_banner(main_page)

            exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
            if exp_btn.is_visible(timeout=5000):
                print(f"✅ Landed directly on {city} Promotions page!")
                return main_page
        except Exception as e:
            print(f"[*] Note on direct navigation: {e}")
            main_page = ensure_main_page(context, main_page)

    # 2. UI Switcher Navigation
    print(f"[*] Opening Account Switcher menu for {city}...")
    try:
        main_page = ensure_main_page(context, main_page)
        user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
        if user_btn.is_visible(timeout=4000):
            user_btn.click()
            time.sleep(1)

            sw_btn = main_page.locator('text="Switch account"').first
            if sw_btn.is_visible(timeout=3000):
                sw_btn.click()
                time.sleep(2)

                for query in [acct, short, f"SAMVREEDDHI MOBILITY {short}", f"Samvreeddhi Mobility Pvt Ltd {short}"]:
                    opt = main_page.locator(f'text="{query}"').first
                    if opt.is_visible(timeout=1500):
                        try:
                            opt.scroll_into_view_if_needed()
                            opt.click()
                            print(f"✅ Selected {city} ({query}) from UI switcher!")
                            time.sleep(4)
                            time.sleep(6)  # Wait for page to fully navigate after switch
                            break
                        except Exception:
                            pass

                # If none of the text queries matched, try scrolling down in the list to find HYD
                if not any(kw in main_page.url for kw in ["HYD", "hyd"]):
                    print(f"[*] Scrolling account list to find HYD P...")
                    account_list = main_page.locator('[data-testid="account-list"], [class*="account"], [class*="switcher"]').first
                    for _ in range(5):
                        try:
                            main_page.keyboard.press("PageDown")
                            time.sleep(1)
                            for query in ["HYD P", "HYD", "Hyderabad", acct, short]:
                                opt = main_page.locator(f'text="{query}"').first
                                if opt.is_visible(timeout=800):
                                    opt.scroll_into_view_if_needed()
                                    opt.click()
                                    print(f"✅ Selected {city} ({query}) from UI switcher (after scroll)!")
                                    time.sleep(6)
                                    break
                        except Exception:
                            pass

        main_page = ensure_main_page(context, main_page)

        # --- CRITICAL: Wait for URL to change away from previous city ---
        # Navigate directly to promotions on whatever org is now active
        time.sleep(3)
        current_url = main_page.url

        if "/orgs/" in current_url:
            current_org = current_url.split("/orgs/")[1].split("/")[0]
            promo_url = f"https://supplier.uber.com/orgs/{current_org}/promotions"
            if "/promotions" not in current_url:
                main_page.goto(promo_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)

            # Check the page header to confirm correct account is loaded
            try:
                header_text = main_page.locator("h1, h2, [class*='org-name'], [class*='account-name']").first.inner_text(timeout=3000)
                print(f"[+] Current account on page: '{header_text}' | URL org: {current_org}")
            except Exception:
                print(f"[+] Current page URL: {current_url}")
        elif "/promotions" not in current_url:
            promo_tab = main_page.locator('a:has-text("Promotions")').first
            if promo_tab.is_visible(timeout=3000):
                promo_tab.click()
                time.sleep(3)

        dismiss_banner(main_page)
        return main_page
    except Exception as e:
        print(f"[*] Note on switcher: {e}")
        return ensure_main_page(context, main_page)


def export_and_download_visual(context: BrowserContext, main_page: Page, target: dict, download_state: dict, seen_files: set = None) -> Path:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    code = target["code"]
    kw = target["file_keyword"]
    max_wait = target.get("max_wait_seconds", 900)
    today = datetime.datetime.now().strftime("%Y%m%d")

    print(f"\n[*] Looking for 'Export' button for {city}...")
    dismiss_banner(main_page)

    exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=3000):
        print(f"❌ Export button not visible on {city} Promotions page! (URL: {main_page.url})")
        return None

    print(f"🎯 Found 'Export' button! Clicking now...")

    if seen_files is None:
        seen_files = set()

    download_state["latest_file"] = None
    trigger_time = time.time()

    try:
        exp_btn.evaluate("b => b.click()")
    except Exception:
        exp_btn.click(force=True)

    print(f"🚀 Export request submitted to Uber backend! Waiting for file download...")

    start_time = time.time()
    last_log = time.time()
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        # 1. Check download state from context listener — skip if already seen
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            if str(download_state["latest_file"]) not in seen_files:
                if is_valid_incentive_file(download_state["latest_file"]):
                    found_file = download_state["latest_file"]
                    break

        # 2. Scan OUT_DIR and USER_DL_DIR — catch .csv AND UUID-named files (no extension)
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.iterdir():
                    if not f.is_file():
                        continue
                    # Skip partial downloads and temp files
                    if f.suffix in [".crdownload", ".tmp", ".part"]:
                        continue
                    # Skip files already claimed by a previous city
                    if str(f) in seen_files:
                        continue
                    try:
                        # Strict: file must have been created AFTER this city's export click
                        if f.stat().st_mtime >= trigger_time and f.stat().st_size > 100:
                            if is_valid_incentive_file(f):
                                dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                if f != dest:
                                    shutil.copy2(str(f), str(dest))
                                found_file = dest
                                seen_files.add(str(f))
                                print(f"\n📥 Found downloaded file: {f.name} -> {dest.name}")
                                break
                    except Exception:
                        pass
            if found_file:
                break

        if found_file:
            break

        if time.time() - last_log >= 15:
            last_log = time.time()
            mins = elapsed // 60
            secs = elapsed % 60
            print(f"   ⏳ Waiting for Uber generation... ({mins}m {secs}s elapsed)", flush=True)

        time.sleep(2)

    # Let any popup tab finish and close
    time.sleep(3)
    ensure_main_page(context, main_page)

    if found_file and found_file.exists():
        dest_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
        dest_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.xlsx"

        if found_file != dest_csv:
            shutil.copy2(str(found_file), str(dest_csv))

        df = pd.read_csv(dest_csv)
        df["City"] = city
        df.to_excel(dest_xlsx, index=False)
        print(f"\n🎉 [SUCCESS] {city} Dataset Downloaded & Converted: {dest_xlsx.name} ({len(df):,} rows)")
        return dest_csv

    print(f"\n⚠️ Timed out waiting for {city} export.")
    return None


def refresh_page_before_export(main_page: Page, city: str, refreshes: int = 3):
    """Refresh the promotions page 2-3 times before clicking Export to ensure clean state."""
    print(f"\n[*] Refreshing page {refreshes}x before Export for {city} (clearing any stale state)...")
    for i in range(1, refreshes + 1):
        try:
            main_page.reload(wait_until="domcontentloaded", timeout=30000)
            print(f"   Refresh {i}/{refreshes} complete")
            time.sleep(3)
        except Exception as e:
            print(f"   Refresh {i} note: {e}")


def cooldown_after_download(city: str, seconds: int = 30):
    """Wait after a download to let popup tabs fully close and network settle."""
    print(f"\n[*] Cooldown: waiting {seconds}s after {city} download before next city...")
    for i in range(seconds, 0, -5):
        print(f"   Cooldown: {i}s remaining...", flush=True)
        time.sleep(5)
    print(f"[+] Cooldown complete. Proceeding to next city.\n")


def run():
    print("===========================================================================")
    print("   LETZRYD - LOCAL VISUAL RUNNER (PRODUCTION v4.8)")
    print("===========================================================================")

    cleanup_locks()
    download_state = {"latest_file": None}

    with sync_playwright() as pw:
        print("[*] Launching Visible Chromium Browser...")
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            downloads_path=str(OUT_DIR),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-default-browser-check"
            ]
        )

        def on_context_download(download):
            print(f"\n📥 [CONTEXT DOWNLOAD EVENT] Suggested filename: {download.suggested_filename}")
            dest = OUT_DIR / download.suggested_filename
            try:
                download.save_as(str(dest))
                download_state["latest_file"] = dest
                print(f"✅ Download saved: {dest.name} ({dest.stat().st_size:,} bytes)")
            except Exception as e:
                print(f"[*] Save note: {e}")

        context.on("download", on_context_download)

        main_page = context.pages[0] if context.pages else context.new_page()

        try:
            Stealth().apply_stealth_sync(main_page)
            print("[+] Stealth mode active")
        except Exception as e:
            print(f"[*] Stealth note: {e}")

        if COOKIES_F.exists():
            cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
            print(f"[+] Loaded {len(cookies)} saved session cookies")

        all_city_dfs = []
        today = datetime.datetime.now().strftime("%Y%m%d")
        seen_files: set = set()  # Track files claimed by previous cities — prevents cross-contamination

        for i, target in enumerate(TARGET_CITIES):
            main_page = switch_to_city_visual(context, main_page, target)
            time.sleep(2)
            # Refresh page 3x before clicking Export to clear any stale state / leftover popup artefacts
            refresh_page_before_export(main_page, target["city"], refreshes=3)
            # Reset download state so we don't accidentally pick up the previous city's late event
            download_state["latest_file"] = None
            csv_path = export_and_download_visual(context, main_page, target, download_state, seen_files)
            if csv_path and csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df["City"] = target["city"]
                    all_city_dfs.append(df)
                except Exception:
                    pass
            # 30s cooldown between cities so popup tabs fully close and network settles
            if i < len(TARGET_CITIES) - 1:
                cooldown_after_download(target["city"], seconds=30)

        if all_city_dfs:
            master_df = pd.concat(all_city_dfs, ignore_index=True)
            master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
            master_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv"

            cols = ["City"] + [c for c in master_df.columns if c != "City"]
            master_df = master_df[cols]

            master_df.to_excel(master_xlsx, index=False)
            master_df.to_csv(master_csv, index=False)

            print("\n" + "=" * 70)
            print(f"🎉 MASTER REPORT CREATED: {master_xlsx}")
            print(f"📊 Total Rows Across All 3 Cities: {len(master_df):,}")
            print("=" * 70)

        print("\n[*] Execution completed successfully. Closing browser in 10 seconds...")
        time.sleep(10)
        context.close()


if __name__ == "__main__":
    run()
