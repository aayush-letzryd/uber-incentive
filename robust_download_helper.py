"""
LETZRYD · ROBUST LOCAL TEST RUNNER
===================================
Tests multi-city switching with permanent main_page reference and popup tab isolation.
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
        "org_uuid": "f7d7968b-43fe-4c15-bfc8-30a82c8ad5b9",
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
    """Ensures we always have a live main page, closing any lingering popups."""
    # Close any extra orphan popup pages
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


def switch_to_city(context: BrowserContext, main_page: Page, target: dict) -> Page:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    code = target["code"]
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

                clicked = False
                for query in [acct, short, f"SAMVREEDDHI MOBILITY {short}", f"Samvreeddhi Mobility Pvt Ltd {short}"]:
                    opt = main_page.locator(f'text="{query}"').first
                    if opt.is_visible(timeout=1500):
                        try:
                            opt.scroll_into_view_if_needed()
                            opt.click()
                            print(f"✅ Selected {city} ({query}) from UI switcher!")
                            clicked = True
                            time.sleep(4)
                            break
                        except Exception:
                            pass

        main_page = ensure_main_page(context, main_page)
        if "/promotions" not in main_page.url:
            if "/orgs/" in main_page.url:
                current_org = main_page.url.split("/orgs/")[1].split("/")[0]
                promo_url = f"https://supplier.uber.com/orgs/{current_org}/promotions"
                main_page.goto(promo_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)
            else:
                promo_tab = main_page.locator('a:has-text("Promotions")').first
                if promo_tab.is_visible(timeout=3000):
                    promo_tab.click()
                    time.sleep(3)

        dismiss_banner(main_page)
        return main_page
    except Exception as e:
        print(f"[*] Note on switcher: {e}")
        return ensure_main_page(context, main_page)


def export_and_download_city(context: BrowserContext, main_page: Page, target: dict, download_state: dict) -> Path:
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

        # 1. Check download state from context listener
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            if is_valid_incentive_file(download_state["latest_file"]):
                found_file = download_state["latest_file"]
                break

        # 2. Scan OUT_DIR and USER_DL_DIR (exclude partial .crdownload / .tmp)
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.glob("*.csv"):
                    if f.is_file() and not f.name.endswith(".crdownload"):
                        try:
                            if f.stat().st_mtime >= (trigger_time - 5) and f.stat().st_size > 100:
                                if is_valid_incentive_file(f):
                                    dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                    if f != dest:
                                        shutil.copy2(str(f), str(dest))
                                    found_file = dest
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

    # Clean up popup tabs before proceeding
    time.sleep(2)
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
