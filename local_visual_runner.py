"""
LETZRYD · LOCAL VISUAL RUNNER (HEADED CHROME MODE v2.1)
======================================================
1. Intercepts popup tab downloads cleanly
2. Maintains active page lifecycle (never crashes when popup tab auto-closes)
3. Switches across Bangalore, Mumbai, and Hyderabad
4. Generates Excel & Master 3-City Dataset
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
        "org_uuid": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "account_name": "Samvreeddhi Mobility Pvt Ltd HYD P",
        "short_name": "HYD P",
        "file_keyword": "HYD_P",
        "max_wait_seconds": 600
    }
]


def get_active_page(context: BrowserContext) -> Page:
    """Always returns a live, non-closed page reference."""
    active_pages = [p for p in context.pages if not p.is_closed()]
    if active_pages:
        return active_pages[0]
    return context.new_page()


def highlight(page: Page, locator):
    try:
        if not page.is_closed():
            locator.evaluate("el => el.style.border = '3px solid #ff0000'")
            time.sleep(0.5)
    except Exception:
        pass


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


def switch_to_city_visual(context: BrowserContext, target: dict) -> Page:
    page = get_active_page(context)
    city = target["city"]
    short = target["short_name"]
    acct = target["account_name"]
    org_uuid = target.get("org_uuid")

    print(f"\n=======================================================")
    print(f"👉 [SWITCHING ACCOUNT] -> {city} ('{short}')")
    print(f"=======================================================")

    # Direct URL navigation
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        print(f"[*] Navigating to {city} URL: {url}")
        try:
            page.goto(url, timeout=45000)
            time.sleep(4)
            page = get_active_page(context)
            dismiss_banner(page)

            exp_btn = page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
            if exp_btn.is_visible(timeout=4000):
                highlight(page, exp_btn)
                print(f"✅ Landed directly on {city} Promotions page!")
                return page
        except Exception as e:
            print(f"[*] Note on direct navigation: {e}")
            page = get_active_page(context)

    # UI Switcher fallback
    print(f"[*] Opening Account Switcher menu for {city}...")
    try:
        page = get_active_page(context)
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

        page = get_active_page(context)
        if "/promotions" not in page.url:
            promo_tab = page.locator('a:has-text("Promotions")').first
            if promo_tab.is_visible(timeout=3000):
                highlight(page, promo_tab)
                promo_tab.click()
                time.sleep(4)

        dismiss_banner(page)
        return page
    except Exception as e:
        print(f"[*] Note on switcher: {e}")
        return get_active_page(context)


def export_and_download_visual(context: BrowserContext, target: dict, download_state: dict) -> Path:
    page = get_active_page(context)
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

    download_state["latest_file"] = None
    trigger_time = time.time()

    try:
        exp_btn.evaluate("b => b.click()")
    except Exception:
        exp_btn.click(force=True)

    print(f"🚀 Export request submitted to Uber backend! Waiting for file download...")
    print(f"   (Watching for download completion on context and disk...)")

    start_time = time.time()
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        # 1. Check if context.on('download') captured it
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            found_file = download_state["latest_file"]
            break

        # 2. Scan OUT_DIR and USER_DL_DIR
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.glob("*"):
                    if f.is_file() and (f.suffix in [".csv", ".crdownload"] or "vehicle_incentives" in f.name.lower()):
                        try:
                            if f.stat().st_mtime >= (trigger_time - 5) and f.stat().st_size > 100:
                                if is_valid_incentive_file(f):
                                    dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                    shutil.copy2(str(f), str(dest))
                                    found_file = dest
                                    break
                        except Exception:
                            pass
            if found_file:
                break

        if found_file:
            break

        if elapsed % 10 == 0 and elapsed > 0:
            mins = elapsed // 60
            secs = elapsed % 60
            print(f"   ⏳ Waiting for Uber generation... ({mins}m {secs}s elapsed)", flush=True)

        time.sleep(2)

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

    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass

    download_state = {"latest_file": None}

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

        page = get_active_page(context)

        if COOKIES_F.exists():
            cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
            print(f"[+] Loaded {len(cookies)} saved session cookies")

        all_city_dfs = []
        today = datetime.datetime.now().strftime("%Y%m%d")

        for target in TARGET_CITIES:
            # Switch city using live page manager
            page = switch_to_city_visual(context, target)
            time.sleep(2)
            
            # Export and download
            csv_path = export_and_download_visual(context, target, download_state)
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
