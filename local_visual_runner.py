"""
LETZRYD · LOCAL VISUAL RUNNER (HEADED CHROME MODE)
===================================================
Opens visible Chrome on your screen so you can watch every step live:
1. Loads authenticated session
2. Switches between Bangalore, Mumbai, and Hyderabad
3. Highlights elements on screen
4. Clicks 'Export' and watches download progress
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

BASE        = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
COOKIES_F   = BASE / "cookies.json"
OUT_DIR     = BASE / "uber_reports"
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
        "max_wait_seconds": 1200
    },
    {
        "city": "Mumbai",
        "code": "MUM",
        "org_uuid": "44cb587c-a690-44b5-94c2-37539500c7d5",
        "account_name": "Samvreeddhi Mobility Pvt. Ltd. MUM P",
        "short_name": "MUM P",
        "file_keyword": "MUM_P",
        "max_wait_seconds": 900
    },
    {
        "city": "Hyderabad",
        "code": "HYD",
        "org_uuid": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "short_name": "HYD P",
        "file_keyword": "HYD_P",
        "max_wait_seconds": 900
    }
]


def highlight(page: Page, locator):
    """Visually highlights an element on screen with a bright red border."""
    try:
        locator.evaluate("el => el.style.border = '3px solid #ff0000'")
        time.sleep(0.5)
    except Exception:
        pass


def dismiss_banner(page: Page):
    try:
        close_btn = page.locator('header svg[data-baseweb="icon"], button[aria-label="Close"]').first
        if close_btn.is_visible(timeout=1500):
            close_btn.click()
            time.sleep(1)
    except Exception:
        pass


def switch_to_city_visual(page: Page, target: dict):
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    org_uuid = target.get("org_uuid")

    print(f"\n=======================================================")
    print(f"👉 [SWITCHING ACCOUNT] -> {city} ('{short}')")
    print(f"=======================================================")

    # Direct URL
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        print(f"[*] Navigating to {city} URL: {url}")
        page.goto(url, timeout=45000)
        time.sleep(4)
        dismiss_banner(page)

        exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
        if exp_btn.is_visible(timeout=4000):
            highlight(page, exp_btn)
            print(f"✅ Landed directly on {city} Promotions page!")
            return True

    # Switcher UI if needed
    print(f"[*] Opening Account Switcher menu for {city}...")
    user_btn = page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
    if user_btn.is_visible(timeout=3000):
        highlight(page, user_btn)
        user_btn.click()
        time.sleep(1)

        sw_btn = page.locator('text="Switch account"').first
        if sw_btn.is_visible(timeout=3000):
            highlight(page, sw_btn)
            sw_btn.click()
            time.sleep(2)

            for query in [acct, short, city]:
                opt = page.locator(f'text="{query}"').first
                if opt.is_visible(timeout=1500):
                    highlight(page, opt)
                    opt.click()
                    time.sleep(1)
                    break

            for query in [acct, short]:
                opt = page.locator(f'text="{query}"').last
                if opt.is_visible(timeout=1500):
                    highlight(page, opt)
                    opt.click()
                    print(f"✅ Selected {city} ({query}) from UI switcher!")
                    time.sleep(4)
                    break

    if "/promotions" not in page.url:
        promo_tab = page.locator('a:has-text("Promotions")').first
        if promo_tab.is_visible(timeout=3000):
            highlight(page, promo_tab)
            promo_tab.click()
            time.sleep(4)

    dismiss_banner(page)
    return True


def export_and_download_visual(page: Page, context: BrowserContext, target: dict) -> Path:
    city = target["city"]
    code = target["code"]
    kw   = target["file_keyword"]
    max_wait = target.get("max_wait_seconds", 900)
    today = datetime.datetime.now().strftime("%Y%m%d")

    print(f"\n[*] Looking for 'Export' button for {city}...")
    dismiss_banner(page)

    exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=3000):
        print(f"❌ Export button not visible on {city} Promotions page! (URL: {page.url})")
        return None

    highlight(page, exp_btn)
    print(f"🎯 Found 'Export' button! Clicking now...")

    download_info = {"file": None}

    def on_download(download):
        print(f"\n📥 [DOWNLOAD EVENT] Suggested filename: {download.suggested_filename}")
        dest = OUT_DIR / download.suggested_filename
        try:
            download.save_as(str(dest))
            download_info["file"] = dest
            print(f"✅ Download saved: {dest.name} ({dest.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"[*] Save note: {e}")

    page.on("download", on_download)

    trigger_time = time.time()
    try:
        exp_btn.evaluate("b => b.click()")
    except Exception:
        exp_btn.click(force=True)

    print(f"🚀 Export request submitted to Uber backend! Waiting for file download...")
    print(f"   (Uber backend takes ~3-12 minutes depending on fleet size. Watching live...)")

    start_time = time.time()
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        if download_info["file"] and download_info["file"].exists() and download_info["file"].stat().st_size > 100:
            found_file = download_info["file"]
            break

        # Scan OUT_DIR and USER_DL_DIR
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.glob("*.csv"):
                    if "vehicle_incentives" in f.name.lower() and kw.lower() in f.name.lower():
                        try:
                            if f.stat().st_mtime >= (trigger_time - 5) and f.stat().st_size > 100:
                                dest = OUT_DIR / f.name
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

        if elapsed % 15 == 0 and elapsed > 0:
            mins = elapsed // 60
            secs = elapsed % 60
            print(f"   ⏳ Waiting for Uber generation... ({mins}m {secs}s elapsed)", flush=True)

        time.sleep(3)

    try:
        page.remove_listener("download", on_download)
    except Exception:
        pass

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


def run():
    print("===========================================================================")
    print("   LETZRYD - LOCAL VISUAL RUNNER (WATCH LIVE ON SCREEN)")
    print("===========================================================================")

    # Clean locks
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass

    with sync_playwright() as pw:
        print("[*] Launching Visible Chrome Browser on your screen...")
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            downloads_path=str(OUT_DIR),
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-default-browser-check"
            ]
        )

        page = context.pages[0] if context.pages else context.new_page()

        if COOKIES_F.exists():
            cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
            print(f"[+] Loaded {len(cookies)} saved session cookies")

        all_city_dfs = []
        today = datetime.datetime.now().strftime("%Y%m%d")

        for target in TARGET_CITIES:
            switch_to_city_visual(page, target)
            csv_path = export_and_download_visual(page, context, target)
            if csv_path and csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    df["City"] = target["city"]
                    all_city_dfs.append(df)
                except Exception:
                    pass

        if all_city_dfs:
            master_df = pd.concat(all_city_dfs, ignore_index=True)
            master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
            master_df.to_excel(master_xlsx, index=False)
            print("\n" + "=" * 70)
            print(f"🎉 MASTER REPORT CREATED: {master_xlsx}")
            print(f"📊 Total Rows Across All 3 Cities: {len(master_df):,}")
            print("=" * 70)

        print("\n[*] Keeping browser open for 15 seconds so you can see final state...")
        time.sleep(15)
        context.close()


if __name__ == "__main__":
    run()
