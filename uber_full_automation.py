"""
LETZRYD · UBER OFFICIAL EXPORT & DOWNLOAD PIPELINE (PRODUCTION v4.8)
====================================================================
- Stable browser lifecycle with popup tab isolation
- Downloads captured via context.on('download')
- Sequential processing of Bangalore, Mumbai, Hyderabad
- Builds Master Consolidated Excel
"""

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
import time
import random
import json
import glob
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from playwright_stealth import Stealth

# ==============================================================================
# CONFIGURATION
# ==============================================================================
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

BASE        = Path(__file__).parent
PROFILE_DIR = BASE / "uber_chrome_profile"
SS_DIR      = BASE / "screenshots"
OUT_DIR     = BASE / "uber_reports"
COOKIES_F   = BASE / "cookies.json"
STATE_F     = BASE / "storage_state.json"
USER_DL_DIR = Path(os.getenv("DOWNLOADS_DIR", str(Path.home() / "Downloads")))

for d in [PROFILE_DIR, SS_DIR, OUT_DIR, USER_DL_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class Log:
    CYAN   = "\033[96m"; BOLD  = "\033[1m"
    GREEN  = "\033[92m"; WARN  = "\033[93m"
    RED    = "\033[91m"; RESET = "\033[0m"
    BLUE   = "\033[94m"

    @staticmethod
    def _t(): return datetime.datetime.now().strftime("%H:%M:%S")

    @classmethod
    def step(cls, n, msg):
        print(f"\n{cls.BOLD}{cls.CYAN}==> [STEP {n}] {msg}{cls.RESET}", flush=True)

    @classmethod
    def info(cls, msg):
        print(f"{cls.BLUE}  [*] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def ok(cls, msg):
        print(f"{cls.GREEN}  [+] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def warn(cls, msg):
        print(f"{cls.WARN}  [!] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def err(cls, msg):
        print(f"{cls.RED}  [-] {cls._t()} | {msg}{cls.RESET}", flush=True)

    @classmethod
    def wait(cls, secs, reason=""):
        txt = f"Waiting {secs}s" + (f" ({reason})" if reason else "")
        print(f"{cls.BLUE}  [~] {cls._t()} | {txt}{cls.RESET}", flush=True)
        time.sleep(secs)


def cleanup_locks():
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        p = PROFILE_DIR / lock
        if p.exists():
            try: p.unlink()
            except Exception: pass


def ensure_main_page(context: BrowserContext, main_page: Page) -> Page:
    """Recover main_page if it's closed. Does NOT close popup tabs during export
    (they may have active downloads in progress)."""
    if main_page is not None and not main_page.is_closed():
        return main_page

    # main_page is gone — recover from remaining open pages
    pages = [p for p in context.pages if not p.is_closed()]
    if pages:
        # Prefer a supplier.uber.com page
        for p in pages:
            if "supplier.uber.com" in p.url:
                return p
        return pages[0]

    return context.new_page()


def close_popup_tabs(context: BrowserContext, main_page: Page):
    """Explicitly close all non-main popup tabs. Call ONLY after download is confirmed complete."""
    for p in list(context.pages):
        if p != main_page:
            try:
                if not p.is_closed():
                    p.close()
            except Exception:
                pass


def load_session(context: BrowserContext) -> bool:
    loaded = False
    if COOKIES_F.exists():
        try:
            cookies = json.loads(COOKIES_F.read_text(encoding="utf-8"))
            if isinstance(cookies, list) and cookies:
                context.add_cookies(cookies)
                Log.ok(f"Loaded {len(cookies)} cached session cookies from {COOKIES_F.name}")
                loaded = True
        except Exception as e:
            Log.warn(f"Cookie load note: {e}")

    if STATE_F.exists() and not loaded:
        # Only load from storage_state if cookies.json had nothing — avoids duplicates
        try:
            state_data = json.loads(STATE_F.read_text(encoding="utf-8"))
            if isinstance(state_data, dict) and "cookies" in state_data and state_data["cookies"]:
                context.add_cookies(state_data["cookies"])
                Log.ok(f"Loaded {len(state_data['cookies'])} session cookies from {STATE_F.name}")
                loaded = True
        except Exception as e:
            Log.warn(f"State load note: {e}")

    return loaded


def is_login_required(page: Page) -> bool:
    """Checks whether the current page is an authentication / login challenge."""
    try:
        url = page.url.lower()
        # Must be on a known auth domain — not just any page containing /login in path
        if any(auth_term in url for auth_term in [
            "auth.uber.com", "login.uber.com", "accounts.google.com",
        ]):
            return True
        # supplier.uber.com/login (exact login path, not /orgs/xxx/settings-login)
        if "supplier.uber.com/login" in url or "supplier.uber.com/sign-in" in url:
            return True
        # Check for auth-specific UI elements (avoid false positives from OTP inputs on dashboard)
        # Only check for email/phone login forms, not general input[type=email]
        auth_loc = page.locator(
            'input#PHONE_NUMBER_OR_EMAIL_ADDRESS, input[name="textValue"][placeholder*="phone"], '
            'button:has-text("Continue with Google"), '
            'h1:has-text("Sign in"), h1:has-text("Log in"), h1:has-text("Welcome back")'
        ).first
        if auth_loc.is_visible(timeout=1000):
            return True
    except Exception:
        pass
    return False


def verify_session_active(page: Page) -> bool:
    """Pre-flight check: navigate to Uber Supplier and confirm session is live."""
    try:
        Log.info("Pre-flight: Verifying session is active on Uber Supplier Portal...")
        page.goto("https://supplier.uber.com", timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)
        dismiss_banner(page)
        
        if is_login_required(page):
            Log.warn(f"❌ Session pre-flight: Login required (URL: {page.url})")
            return False

        user_menu = page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
        if user_menu.is_visible(timeout=5000):
            Log.ok(f"✅ Session pre-flight passed (user menu active on: {page.url})")
            return True

        if "supplier.uber.com" in page.url and not is_login_required(page):
            Log.ok(f"✅ Session pre-flight passed. Landed on: {page.url}")
            return True

        Log.warn(f"❌ Session pre-flight failed — unknown state on: {page.url}")
        return False
    except Exception as e:
        Log.warn(f"Session pre-flight note: {e}")
        return False


def dismiss_banner(page: Page):
    """Dismisses banners, survey popups, feedback dialogs, and modal backdrops that could intercept clicks."""
    try:
        if not page.is_closed():
            # 1. Close icon or banner buttons
            close_btn = page.locator(
                'header svg[data-baseweb="icon"], button[aria-label="Close"], '
                'div[role="dialog"] button:has-text("Dismiss"), button:has-text("Not now"), '
                'button:has-text("Skip"), button:has-text("Maybe later"), button:has-text("Got it"), '
                '#onetrust-accept-btn-handler, button:has-text("Accept all")'
            ).first
            if close_btn.is_visible(timeout=1000):
                close_btn.click()
                time.sleep(0.5)
    except Exception:
        pass


def is_valid_incentive_file(file_path: Path) -> bool:
    """Validates downloaded CSV header for Vehicle name and Number plate (case-insensitive, UTF-8 BOM safe)."""
    try:
        if not file_path.exists() or file_path.stat().st_size < 100:
            return False
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            header = f.readline().lower()
            return "vehicle name" in header and "number plate" in header
    except Exception:
        return False


ORG_CACHE_FILE = BASE / "org_uuids.json"


def load_cached_org_uuids() -> dict:
    if ORG_CACHE_FILE.exists():
        try:
            return json.loads(ORG_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "BLR": "ebb10afb-c08b-463e-a4fa-33b64674adfd",
        "MUM": "44cb587c-a690-44b5-94c2-37539500c7d5",
        "HYD": "f7d7968b-43fe-4c15-bfc8-30a82c8ad5b9"
    }


def save_cached_org_uuid(code: str, uuid: str):
    try:
        cached = load_cached_org_uuids()
        cached[code] = uuid
        ORG_CACHE_FILE.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        Log.ok(f"Saved discovered Org UUID for {code}: {uuid} -> {ORG_CACHE_FILE.name}")
    except Exception as e:
        Log.warn(f"Note saving org UUID: {e}")


# ── Secrets: sourced from GCP Secret Manager via Cloud Run --set-secrets ──
UBER_EMAIL    = os.getenv("UBER_EMAIL", "uber.india@letzryd.com")
UBER_PASSWORD = os.getenv("UBER_PASSWORD", "")   # Set via: --set-secrets UBER_PASSWORD=UBER_PASSWORD:latest
SHEET_ID      = os.getenv("SHEET_ID", "1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4")
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0" if SHEET_ID else ""


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
        Log.warn(f"Sheet fetch note: {e}")
    return None, None, ""


def poll_for_new_otp(initial_date, initial_code, timeout_seconds=90):
    Log.info(f"Waiting for new Uber OTP in Google Sheet (Timeout: {timeout_seconds}s)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        code, d_str, msg = get_current_sheet_state()
        if code and (code != initial_code or d_str != initial_date):
            Log.ok(f"Retrieved new OTP from Google Sheet: {code} (at {d_str})")
            return code
        time.sleep(4)
    return None


def handle_otp_input(page: Page, initial_sheet_date: str, initial_sheet_code: str):
    Log.step("2FA", "2FA SMS OTP Verification Screen Detected")
    otp = poll_for_new_otp(initial_sheet_date, initial_sheet_code, timeout_seconds=60)
    if not otp:
        otp, _, _ = get_current_sheet_state()

    if otp and len(otp) == 4:
        Log.ok(f"Entering 4-digit OTP: {otp}")
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

        time.sleep(1)
        next_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button[type="submit"]').first
        if next_btn.is_visible():
            next_btn.click()
        else:
            page.keyboard.press("Enter")
        time.sleep(5)


def save_session_state(context: BrowserContext):
    try:
        cookies = context.cookies()
        if cookies:
            COOKIES_F.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
            Log.ok(f"Saved {len(cookies)} cookies to {COOKIES_F.name}")
        storage = context.storage_state()
        if storage:
            STATE_F.write_text(json.dumps(storage, indent=2), encoding="utf-8")
            Log.ok(f"Saved storage_state to {STATE_F.name}")
    except Exception as e:
        Log.warn(f"Note saving session: {e}")


def login_with_google(page: Page, context: BrowserContext) -> bool:
    Log.step("GOOGLE_AUTH", "Attempting Login via Google Account OAuth...")
    init_code, init_date, _ = get_current_sheet_state()
    try:
        google_btn = page.locator('button:has-text("Continue with Google"), button:has-text("Google"), [data-testid*="google"]').first
        if google_btn.is_visible(timeout=5000):
            Log.info("Clicking 'Continue with Google'...")
            google_btn.click()
            time.sleep(4)

        # 1. Google Email
        g_email = page.locator('input[type="email"], input#identifierId').first
        if g_email.is_visible(timeout=6000):
            Log.info(f"Entering Google email: {UBER_EMAIL}")
            g_email.fill("")
            g_email.type(UBER_EMAIL, delay=30)
            time.sleep(0.5)
            next_btn = page.locator('#identifierNext button, button:has-text("Next")').first
            if next_btn.is_visible():
                next_btn.click()
            else:
                page.keyboard.press("Enter")
            time.sleep(5)

        # 2. Google Password
        g_pwd = page.locator('input[type="password"], input[name="Passwd"]').first
        if g_pwd.is_visible(timeout=8000):
            Log.info("Entering Google password...")
            g_pwd.fill("")
            g_pwd.type(UBER_PASSWORD, delay=30)
            time.sleep(0.5)
            next_btn = page.locator('#passwordNext button, button:has-text("Next")').first
            if next_btn.is_visible():
                next_btn.click()
            else:
                page.keyboard.press("Enter")
            time.sleep(6)

        # 3. Google 2FA / Gmail OTP Verification
        if any(w in page.content().lower() for w in ["verification code", "2-step", "enter code", "get a verification"]):
            Log.info("Google 2-Step Verification detected. Polling Google Sheet for OTP...")
            otp = poll_for_new_otp(init_date, init_code, timeout_seconds=90)
            if not otp:
                otp, _, _ = get_current_sheet_state()
            if otp:
                Log.ok(f"Entering Google OTP: {otp}")
                otp_input = page.locator('input#idvPin, input[type="tel"], input[name="Pin"]').first
                if otp_input.is_visible(timeout=4000):
                    otp_input.fill(otp)
                    time.sleep(0.5)
                    next_btn = page.locator('#idvPreregisteredPhoneNext button, button:has-text("Next")').first
                    if next_btn.is_visible():
                        next_btn.click()
                    else:
                        page.keyboard.press("Enter")
                    time.sleep(6)

        # 4. Wait for redirect back to supplier.uber.com
        for _ in range(15):
            if "supplier.uber.com" in page.url and "accounts.google.com" not in page.url and "auth.uber.com" not in page.url:
                Log.ok(f"🎉 Google OAuth Login successful! Landed on: {page.url}")
                save_session_state(context)
                return True
            time.sleep(2)
    except Exception as e:
        Log.warn(f"Google login flow note: {e}")
    return False


def ensure_login(page: Page, context: BrowserContext) -> bool:
    time.sleep(2)
    dismiss_banner(page)

    # Bug 1 Fix: any valid supplier page (not just /orgs/) confirms active session
    if "supplier.uber.com" in page.url and not is_login_required(page):
        Log.ok(f"Active session confirmed on {page.url}")
        save_session_state(context)
        return True

    Log.step("AUTH", "Automated Uber Login Engine (Password / SMS OTP / Google OAuth)...")

    # Only navigate to login page if currently on an auth/login page or unknown page.
    # Do NOT navigate away from a valid supplier page — that would drop the session.
    if not is_login_required(page) and "supplier.uber.com" not in page.url:
        try:
            page.goto("https://supplier.uber.com/login", timeout=30000, wait_until="domcontentloaded")
            time.sleep(4)
            dismiss_banner(page)
        except Exception:
            pass

    init_code, init_date, _ = get_current_sheet_state()

    # 1. Check for 'Log in' or 'Sign in' buttons on landing page
    try:
        landing_login = page.locator('a:has-text("Log in"), button:has-text("Log in"), a:has-text("Sign in"), button:has-text("Sign in")').first
        if landing_login.is_visible(timeout=3000):
            landing_login.click()
            time.sleep(4)
    except Exception:
        pass

    # Strategy 1: Standard Uber Email + Password / SMS OTP
    try:
        email_input = page.locator('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS, input[name="textValue"]').first
        if email_input.is_visible(timeout=5000):
            Log.info(f"Entering login email: {UBER_EMAIL}")
            email_input.fill("")
            email_input.type(UBER_EMAIL, delay=30)
            time.sleep(0.5)
            continue_btn = page.locator('button:has-text("Continue"), button[type="submit"], button#forward-button').first
            if continue_btn.is_visible():
                continue_btn.click()
            else:
                page.keyboard.press("Enter")
            time.sleep(5)

        # Password or More Options
        pwd_inputs = page.locator('input[type="password"]')
        if pwd_inputs.count() > 0 and pwd_inputs.first.is_visible():
            Log.info("Entering password directly...")
            pwd_inputs.first.fill("")
            pwd_inputs.first.type(UBER_PASSWORD, delay=30)
            time.sleep(0.5)
            submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"], button#forward-button').first
            if submit_btn.is_visible():
                submit_btn.click()
            else:
                page.keyboard.press("Enter")
            time.sleep(5)
        else:
            more_opts = page.get_by_text("More options", exact=False).first
            if more_opts.is_visible(timeout=3000):
                Log.info("Clicking 'More options'...")
                more_opts.click()
                time.sleep(2)

                see_all = page.get_by_text("See all options", exact=False).first
                if see_all.is_visible(timeout=2000):
                    see_all.click()
                    time.sleep(2)

                pwd_option = page.get_by_text("Password", exact=True).first
                if not pwd_option.is_visible(timeout=2000):
                    pwd_option = page.locator('div[role="dialog"] >> text="Password"').first

                if pwd_option.is_visible(timeout=3000):
                    Log.info("Selecting 'Password' option...")
                    pwd_option.click()
                    time.sleep(2.5)

                    pwd_input = page.locator('input[type="password"]').first
                    if pwd_input.is_visible(timeout=5000):
                        Log.info("Entering password...")
                        pwd_input.fill("")
                        pwd_input.type(UBER_PASSWORD, delay=30)
                        time.sleep(0.5)
                        submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"], button#forward-button').first
                        if submit_btn.is_visible():
                            submit_btn.click()
                        else:
                            page.keyboard.press("Enter")
                        time.sleep(6)

        # 2FA SMS OTP if prompted
        time.sleep(2)
        if "code" in page.content().lower() or page.locator('input[type="tel"]').count() > 0 or "verification" in page.content().lower():
            handle_otp_input(page, init_date, init_code)

        # Check if logged in
        for _ in range(8):
            if "supplier.uber.com" in page.url and not is_login_required(page):
                Log.ok(f"🎉 Successfully logged in via standard auth! Landed on: {page.url}")
                save_session_state(context)
                return True
            time.sleep(2)
    except Exception as e:
        Log.warn(f"Standard auth note: {e}")

    # Strategy 2: Fallback to Google Account OAuth
    if is_login_required(page) or "accounts.google.com" in page.url:
        Log.warn("Standard login not confirmed. Initiating Google Account OAuth fallback...")
        if login_with_google(page, context):
            return True

    return "supplier.uber.com" in page.url and not is_login_required(page)


def switch_to_city(context: BrowserContext, main_page: Page, target: dict, previous_orgs: set) -> Page:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    code = target["code"]
    short = target["short_name"]
    acct = target["account_name"]

    cached_orgs = load_cached_org_uuids()
    org_uuid = target.get("org_uuid") or cached_orgs.get(code)
    Log.step("SWITCH", f"Opening {city} ('{short}')")

    # 1. Direct URL navigation if org_uuid is known
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        Log.info(f"Direct navigating to {city} URL: {url}...")
        try:
            main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
            Log.wait(4, f"Loading {city} promotions page")
            main_page = ensure_main_page(context, main_page)
            dismiss_banner(main_page)

            # Check if redirected to auth
            if is_login_required(main_page):
                Log.warn(f"Login required (detected URL: {main_page.url})! Triggering automated login...")
                if ensure_login(main_page, context):
                    main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    time.sleep(4)
                    dismiss_banner(main_page)

            # Bug 2 Fix: require the correct org UUID in the URL — not just any non-login page
            if f"/orgs/{org_uuid}" in main_page.url:
                exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
                if exp_btn.is_visible(timeout=8000):
                    Log.ok(f"Direct URL verified for {city} via Org UUID ({org_uuid})!")
                    return main_page
                else:
                    Log.warn(f"On correct org URL but Export button not visible for {city} — falling through to UI Switcher.")
        except Exception as e:
            Log.warn(f"Direct navigation note: {e}")
            main_page = ensure_main_page(context, main_page)

    # 2. UI Switcher Navigation with JS Progressive Container Scrolling
    for attempt in range(1, 4):
        Log.info(f"Attempt {attempt}/3: Opening Account Switcher UI for {city}...")
        try:
            main_page = ensure_main_page(context, main_page)
            user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
            if not user_btn.is_visible(timeout=4000):
                main_page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first

            user_btn.click()
            Log.wait(1, "Opening user menu")

            sw_btn = main_page.locator('text="Switch account"').first
            if not sw_btn.is_visible(timeout=3000):
                Log.warn(f"'Switch account' option not visible in user menu on attempt {attempt}")
                continue

            sw_btn.click()
            Log.wait(2, "Opening account list")

            # Progressive Scroll & Smart Item Search inside the Switcher Container
            switch_result = main_page.evaluate("""(cityTarget) => {
                const isTarget = (txt) => {
                    const t = txt.toUpperCase();
                    if (cityTarget === 'HYD') {
                        // Match HYD P or Hyderabad P, strictly exclude HYD I, II, III, IV, V
                        if (!t.includes('HYD') && !t.includes('HYDERABAD')) return false;
                        if (!t.includes(' P') && !t.includes(' P.') && !t.includes(' PVT')) return false;
                        if (t.includes('HYD I') || t.includes('HYD II') || t.includes('HYD III') || t.includes('HYD IV') || t.includes('HYD V')) return false;
                        return true;
                    } else if (cityTarget === 'MUM') {
                        return (t.includes('MUM') || t.includes('MUMBAI')) && (t.includes(' P') || t.includes(' PVT')) && !t.includes('MUM I') && !t.includes('MUM II');
                    } else if (cityTarget === 'BLR') {
                        return (t.includes('BLR') || t.includes('BANGALORE')) && (t.includes(' P') || t.includes(' PVT'));
                    }
                    return false;
                };

                const allDivs = Array.from(document.querySelectorAll('div, ul, section'));
                const containers = allDivs.filter(el => {
                    const s = window.getComputedStyle(el);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                });
                const container = containers[containers.length - 1];

                // Scroll container to top first so items like HYD P are visible
                if (container) container.scrollTop = 0;

                const candidates = Array.from(document.querySelectorAll('div, li, button, span, [role="radio"], [role="menuitem"]'));
                for (let el of candidates) {
                    const txt = el.innerText ? el.innerText.trim() : '';
                    if (isTarget(txt) && txt.length < 80) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        el.click();
                        return { success: true, matchedText: txt };
                    }
                }

                if (container) {
                    for (let pos = 100; pos <= container.scrollHeight; pos += 100) {
                        container.scrollTop = pos;
                        for (let el of candidates) {
                            const txt = el.innerText ? el.innerText.trim() : '';
                            if (isTarget(txt) && txt.length < 80) {
                                el.scrollIntoView({ behavior: 'instant', block: 'center' });
                                el.click();
                                return { success: true, matchedText: txt };
                            }
                        }
                    }
                }

                return { success: false };
            }""", code)

            if switch_result.get("success"):
                Log.ok(f"Switcher clicked item: '{switch_result.get('matchedText')}'")
                time.sleep(6)  # Wait for navigation

            main_page = ensure_main_page(context, main_page)
            time.sleep(2)
            current_url = main_page.url

            new_org = None
            if "/orgs/" in current_url:
                new_org = current_url.split("/orgs/")[1].split("/")[0]

            # Anti-contamination check:
            if new_org and new_org not in previous_orgs:
                Log.ok(f"SUCCESS: Switched to {city}! Active Org UUID: {new_org}")
                save_cached_org_uuid(code, new_org)
                target["org_uuid"] = new_org

                promo_url = f"https://supplier.uber.com/orgs/{new_org}/promotions"
                if "/promotions" not in main_page.url:
                    main_page.goto(promo_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)

                dismiss_banner(main_page)
                return main_page
            else:
                Log.warn(f"Org UUID ({new_org}) still matches previous city ({previous_orgs})! Retrying switcher...")
                time.sleep(2)

        except Exception as e:
            Log.warn(f"Switcher attempt {attempt} note: {e}")
            time.sleep(2)

    raise RuntimeError(f"FATAL: Failed to switch to {city}. URL is still on previous city org ({main_page.url}). Aborting export to prevent data contamination!")


def export_and_download_city(context: BrowserContext, main_page: Page, target: dict, download_state: dict, seen_files: set = None) -> Path:
    main_page = ensure_main_page(context, main_page)
    city = target["city"]
    code = target["code"]
    kw   = target["file_keyword"]
    max_wait = target.get("max_wait_seconds", 900)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist_tz).strftime("%Y%m%d")
    Log.step("EXPORT", f"Triggering Official Export & Download for {city} ({code})")

    dismiss_banner(main_page)

    exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=2000):
        try:
            ss_path = SS_DIR / f"missing_export_{code.lower()}.png"
            main_page.screenshot(path=str(ss_path))
        except Exception:
            pass
        Log.err(f"Export button not visible on {city} Promotions page! (URL: {main_page.url})")
        return None

    if seen_files is None:
        seen_files = set()

    download_state["latest_file"] = None
    trigger_time = time.time()
    Log.info(f"Clicking 'Export' button for {city}...")
    try:
        exp_btn.scroll_into_view_if_needed(timeout=5000)
        exp_btn.click(timeout=8000)
    except Exception:
        try:
            exp_btn.evaluate("b => b.click()")
        except Exception:
            exp_btn.click(force=True)

    Log.ok(f"Export triggered for {city}! Monitoring download (up to {max_wait//60} mins)...")

    start_time = time.time()
    last_log = time.time() - 5
    found_file = None

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        # 1. Check download state from context listener — skip if already seen
        if download_state.get("latest_file") and download_state["latest_file"].exists():
            if str(download_state["latest_file"]) not in seen_files:
                if is_valid_incentive_file(download_state["latest_file"]):
                    found_file = download_state["latest_file"]
                    seen_files.add(str(found_file))
                    break

        # 2. Scan OUT_DIR and USER_DL_DIR — catch .csv AND UUID-named files (no extension)
        for search_dir in [OUT_DIR, USER_DL_DIR]:
            if search_dir.exists():
                for f in search_dir.iterdir():
                    if not f.is_file():
                        continue
                    if f.suffix in [".crdownload", ".tmp", ".part"]:
                        continue
                    if str(f) in seen_files:
                        continue
                    try:
                        # Strict trigger_time check with 3s drift tolerance for container filesystems
                        if f.stat().st_mtime >= (trigger_time - 3.0) and f.stat().st_size > 100:
                            if is_valid_incentive_file(f):
                                dest = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
                                if f != dest:
                                    shutil.copy2(str(f), str(dest))
                                found_file = dest
                                seen_files.add(str(f))
                                seen_files.add(str(dest))
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
            Log.info(f"Still waiting on Uber backend export... ({mins}m {secs}s / {max_wait//60}m)")

        time.sleep(2)

    # Download is confirmed (or timed out) — NOW it is safe to close popup tabs
    time.sleep(2)
    close_popup_tabs(context, main_page)

    if found_file and found_file.exists():
        dest_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.csv"
        dest_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_{code}_P.xlsx"

        if found_file != dest_csv:
            shutil.copy2(str(found_file), str(dest_csv))
        seen_files.add(str(dest_csv))

        try:
            df = pd.read_csv(dest_csv, encoding="utf-8-sig", low_memory=False, dtype=str)
            df["City"] = city
            df.to_excel(dest_xlsx, index=False)
            sample_plates = df["Number plate"].dropna().head(5).tolist() if "Number plate" in df.columns else []
            Log.ok(f"✅ Saved official dataset ({len(df):,} rows) -> {dest_xlsx.name}")
            Log.info(f"🔍 Plate Sanity Check ({city}): Sample plates -> {sample_plates}")
            return dest_csv
        except Exception as e:
            # Bug 4 Fix Part A: return None — do NOT return the unreadable corrupt path
            Log.err(f"CSV read/Excel conversion failed for {city}: {e} — treating as failed export.")
            return None

    Log.warn(f"Timed out after {max_wait}s waiting for {city} export.")
    return None


def get_browser_launch_config():
    is_container = (
        os.path.exists("/.dockerenv")
        or os.getenv("K_SERVICE") is not None
        or os.getenv("CONTAINER") == "true"
        or sys.platform.startswith("linux")
    )
    
    headless_env = os.getenv("HEADLESS")
    if headless_env is not None:
        headless = headless_env.lower() in ("true", "1", "yes")
    else:
        headless = is_container

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-default-browser-check",
        "--lang=en-IN,en"
    ]

    if headless:
        args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ])

    return headless, args


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 75)
    print("   LETZRYD - UBER OFFICIAL EXPORT & DOWNLOAD ENGINE (3 CITIES)")
    print("   Bangalore | Mumbai | Hyderabad")
    print("=" * 75)

    cleanup_locks()
    headless, args = get_browser_launch_config()
    download_state = {"latest_file": None}

    with sync_playwright() as pw:
        Log.info(f"Launching Browser (Headless: {headless})...")
        
        launch_kwargs = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": headless,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "accept_downloads": True,
            "downloads_path": str(OUT_DIR),
            "ignore_default_args": ["--enable-automation"],
            "args": args
        }

        context = pw.chromium.launch_persistent_context(**launch_kwargs)

        try:
            def on_context_download(download):
                dest = OUT_DIR / download.suggested_filename
                try:
                    download.save_as(str(dest))
                    download_state["latest_file"] = dest
                    Log.ok(f"📥 Context Download Event: {download.suggested_filename}")
                    Log.ok(f"✅ Download saved: {dest.name} ({dest.stat().st_size:,} bytes)")
                except Exception:
                    pass

            context.on("download", on_context_download)
            context.on("page", lambda p: p.on("download", on_context_download))

            main_page = context.pages[0] if context.pages else context.new_page()
            main_page.on("download", on_context_download)
            
            try:
                Stealth().apply_stealth_sync(main_page)
                Log.ok("Stealth mode active")
            except Exception as e:
                Log.warn(f"Stealth apply note: {e}")

            load_session(context)

            # ── PRE-FLIGHT SESSION CHECK (Fix #1) ──────────────────────────────
            # Validate cookies are still live BEFORE entering city loop.
            # If session expired, trigger login immediately so city 1 doesn't waste 3 mins.
            if not verify_session_active(main_page):
                Log.warn("Session cookies expired or invalid. Triggering automated login now...")
                if not ensure_login(main_page, context):
                    raise RuntimeError("Pre-flight login failed. Cannot proceed without authenticated session.")
            # ───────────────────────────────────────────────────────────────────

            all_city_dfs = []
            ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            today = datetime.datetime.now(ist_tz).strftime("%Y%m%d")
            seen_files: set = set()      # Track files claimed by previous cities — prevents cross-contamination
            previous_orgs: set = set()   # Track org UUIDs of prior cities — prevents export on wrong org

            for i, target in enumerate(TARGET_CITIES):
                city_name = target["city"]
                try:
                    main_page = switch_to_city(context, main_page, target, previous_orgs)
                    time.sleep(2)
                    # ── 1 Clean page refresh + 7s DOM stabilization ──────────────────
                    Log.info(f"Performing 1 clean page refresh for {city_name}...")
                    try:
                        main_page.reload(wait_until="domcontentloaded", timeout=30000)
                        Log.info(f"  Reload complete. Stabilizing DOM for 7s before clicking Export...")
                        time.sleep(7)
                        Log.ok(f"  DOM fully hydrated and ready!")
                        # ── Post-reload session guard ──────────────────────────────
                        if is_login_required(main_page):
                            Log.warn(f"Session dropped during {city_name} reload! Re-logging in...")
                            if ensure_login(main_page, context):
                                org_uuid = target.get("org_uuid", "")
                                if org_uuid:
                                    main_page.goto(f"https://supplier.uber.com/orgs/{org_uuid}/promotions",
                                                   timeout=30000, wait_until="domcontentloaded")
                                    time.sleep(5)
                        # ───────────────────────────────────────────────────────────
                    except Exception as e:
                        Log.warn(f"  Refresh note: {e}")
                        time.sleep(3)

                    # Reset download state so previous city's late event is not picked up
                    download_state["latest_file"] = None
                    # Bug 5 Fix: save original main_page reference before export popup might open
                    original_main_page = main_page
                    csv_path = export_and_download_city(context, main_page, target, download_state, seen_files)
                    main_page = ensure_main_page(context, original_main_page)

                    # Bug 4 Fix: no raise e — log CSV failure and skip this city gracefully
                    if csv_path and csv_path.exists():
                        try:
                            df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False, dtype=str)
                            df["City"] = city_name
                            all_city_dfs.append(df)
                            Log.ok(f"✅ {city_name}: {len(df):,} rows collected.")
                            # Record this city's org UUID so next city can't use it
                            if target.get("org_uuid"):
                                previous_orgs.add(target["org_uuid"])
                        except Exception as e:
                            Log.err(f"Failed to read CSV for {city_name}: {e} — skipping this city's data.")
                    else:
                        Log.warn(f"No CSV produced for {city_name} — skipping.")

                except Exception as e:
                    # Bug 3 Fix: per-city isolation — one city failure does NOT abort remaining cities
                    Log.err(f"City {city_name} failed with error: {e}. Continuing with remaining cities...")
                    try:
                        main_page = ensure_main_page(context, main_page)
                    except Exception:
                        pass

                # 20s cooldown between cities so popup tabs fully close and network settles
                if i < len(TARGET_CITIES) - 1:
                    Log.info(f"Cooldown: 20s after {city_name} before proceeding...")
                    for s in range(20, 0, -5):
                        Log.info(f"  Cooldown: {s}s remaining...")
                        time.sleep(5)

            if all_city_dfs:
                master_df = pd.concat(all_city_dfs, ignore_index=True)
                master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
                master_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv"

                cols = ["City"] + [c for c in master_df.columns if c != "City"]
                master_df = master_df[cols]

                master_df.to_excel(master_xlsx, index=False)
                master_df.to_csv(master_csv, index=False)

                Log.ok("=" * 70)
                Log.ok(f"🎉 MASTER CONSOLIDATED REPORT GENERATED SUCCESSFULLY!")
                Log.ok(f"📁 Excel: {master_xlsx}")
                Log.ok(f"📊 Total Rows Across All 3 Cities: {len(master_df):,}")
                Log.ok("=" * 70)

        finally:
            Log.info("Closing browser context cleanly...")
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
