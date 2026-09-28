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
DISCOVERED_ORGS_FILE = BASE / "org_uuids_discovered.json"


def infer_city_from_name(name: str) -> str:
    """Infers standard operational city from fleet organization name."""
    n = name.upper()
    if "BLR" in n or "BANGALORE" in n or "BENGALURU" in n:
        return "Bangalore"
    elif "HYD" in n or "HYDERABAD" in n:
        return "Hyderabad"
    elif "MUM" in n or "MUMBAI" in n:
        return "Mumbai"
    elif "MASTER" in n or "INDIA" in n:
        return "All India"
    else:
        return "Other"


def discover_available_orgs(main_page: Page) -> list:
    """Dynamically scans the Uber account switcher drawer to discover all sub-accounts/sub-orgs."""
    discovered = []
    try:
        Log.step("DISCOVERY", "Discovering all fleet sub-orgs dynamically from Account Switcher...")
        # Open User Menu
        user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first
        if not user_btn.is_visible(timeout=5000):
            main_page.goto("https://supplier.uber.com/", timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)
            user_btn = main_page.locator('[data-testid="user-menu-button"], header img, header button:has(svg)').first

        if user_btn.is_visible(timeout=5000):
            user_btn.click()
            time.sleep(1.5)
            sw_btn = main_page.locator('text="Switch account"').first
            if sw_btn.is_visible(timeout=3000):
                sw_btn.click()
                time.sleep(2)

                # Progressive scroll inside the switcher drawer to capture all virtualized DOM nodes
                raw_items = main_page.evaluate("""() => {
                    const allDivs = Array.from(document.querySelectorAll('div, ul, section'));
                    const containers = allDivs.filter(el => {
                        const s = window.getComputedStyle(el);
                        return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                    });
                    const container = containers[containers.length - 1];

                    const found = [];
                    const scan = () => {
                        const elements = Array.from(document.querySelectorAll('[data-testid^="org-select-"]'));
                        for (let el of elements) {
                            const testid = el.getAttribute('data-testid') || '';
                            const text = (el.innerText || '').trim();
                            if (testid.startsWith('org-select-')) {
                                const uuid = testid.replace('org-select-', '');
                                found.push({ testid, uuid, text });
                            }
                        }
                    };

                    scan();
                    if (container) {
                        for (let pos = 50; pos <= container.scrollHeight; pos += 50) {
                            container.scrollTop = pos;
                            scan();
                        }
                    }
                    return found;
                }""")

                # Close the switcher drawer
                try:
                    main_page.keyboard.press("Escape")
                except Exception:
                    pass

                seen_uuids = set()
                for item in raw_items:
                    uuid = item.get("uuid", "").strip()
                    name = item.get("text", "").split("\n")[0].strip()
                    if uuid and uuid not in seen_uuids and name:
                        seen_uuids.add(uuid)
                        city = infer_city_from_name(name)
                        slug = re.sub(r'[^A-Za-z0-9_]+', '_', name).strip('_')
                        discovered.append({
                            "name": name,
                            "uuid": uuid,
                            "city": city,
                            "slug": slug,
                            "max_wait_seconds": 900 if "BLR" in name.upper() else 600
                        })

                if discovered:
                    Log.ok(f"✅ Discovered {len(discovered)} total sub-orgs dynamically!")
                    try:
                        DISCOVERED_ORGS_FILE.write_text(json.dumps(discovered, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return discovered
    except Exception as e:
        Log.warn(f"Dynamic discovery note: {e}")

    # Fallback to cached org_uuids_discovered.json if drawer discovery failed
    if DISCOVERED_ORGS_FILE.exists():
        try:
            cached = json.loads(DISCOVERED_ORGS_FILE.read_text(encoding="utf-8"))
            if cached:
                Log.ok(f"Loaded {len(cached)} sub-orgs from cached {DISCOVERED_ORGS_FILE.name}")
                for o in cached:
                    if "slug" not in o:
                        o["slug"] = re.sub(r'[^A-Za-z0-9_]+', '_', o["name"]).strip('_')
                    if "max_wait_seconds" not in o:
                        o["max_wait_seconds"] = 900 if "BLR" in o.get("name", "").upper() else 600
                return cached
        except Exception:
            pass

    return []


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
UBER_EMAIL     = os.getenv("UBER_EMAIL", "uber.india@letzryd.com")
UBER_PASSWORD  = os.getenv("UBER_PASSWORD", "")   # Uber portal password — set via Secret Manager
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "Letzryd@12345")  # Google/Gmail password for OAuth fallback
SHEET_ID       = os.getenv("SHEET_ID") or "1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4"
SHEET_CSV_URL  = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"


def get_current_sheet_state():
    try:
        res = requests.get(SHEET_CSV_URL, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                first_msg  = str(df.iloc[0, 0])
                first_from = str(df.iloc[0, 1]) if df.shape[1] >= 2 else ""
                first_date = str(df.iloc[0, 2]) if df.shape[1] >= 3 else ""
                match = re.search(r'\b(\d{4,6})\b', first_msg)
                code = match.group(1) if match else None
                # Flag if this looks like an Uber SMS (sender contains UBER)
                is_uber = "uber" in first_from.lower() or "uber" in first_msg.lower()
                return code, first_date, first_msg, is_uber
    except Exception as e:
        Log.warn(f"Sheet fetch note: {e}")
    return None, None, "", False


def poll_for_new_otp(initial_date, initial_code, timeout_seconds=90):
    Log.info(f"Waiting for new Uber OTP in Google Sheet (Timeout: {timeout_seconds}s)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        code, d_str, msg, is_uber = get_current_sheet_state()
        if code and (code != initial_code or d_str != initial_date):
            # Prefer Uber-tagged messages; accept any new OTP code as fallback
            if is_uber:
                Log.ok(f"Retrieved Uber OTP from Google Sheet: {code} (from Uber SMS at {d_str})")
                return code
            else:
                # Non-Uber SMS — keep polling, but save as fallback
                Log.info(f"New code {code} seen but not from Uber (msg: {msg[:60]}...). Continuing to wait...")
        time.sleep(1)  # Poll every 1 second — sheet only keeps 1 row, can't miss the window
    # Last resort: only return if it's actually from Uber — never return false positives like year 2026
    code, d_str, msg, is_uber = get_current_sheet_state()
    if code and is_uber:
        Log.warn(f"OTP timeout — using last-resort Uber code from sheet: {code}")
        return code
    return None


def handle_otp_input(page: Page, initial_sheet_date: str, initial_sheet_code: str):
    Log.step("2FA", "2FA SMS OTP Verification Screen Detected")
    otp = poll_for_new_otp(initial_sheet_date, initial_sheet_code, timeout_seconds=90)
    if not otp:
        otp, _, _, _ = get_current_sheet_state()

    if otp and (len(otp) == 4 or len(otp) == 6):
        Log.ok(f"Entering {len(otp)}-digit OTP: {otp}")
        digit_inputs = page.locator('input[type="tel"], input[aria-label*="digit"], input[maxlength="1"]').all()
        if len(digit_inputs) >= len(otp):
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
        btn_clicked = False
        try:
            if next_btn.is_visible() and next_btn.is_enabled(timeout=2000):
                next_btn.click()
                btn_clicked = True
        except Exception:
            pass
        if not btn_clicked:
            page.keyboard.press("Enter")
        time.sleep(5)


def save_session_state(context: BrowserContext):
    try:
        cookies = context.cookies()
        if cookies:
            far_future = time.time() + 31536000  # +1 year
            for c in cookies:
                if "expires" in c and (c["expires"] is None or c["expires"] < far_future):
                    c["expires"] = far_future
            COOKIES_F.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
            Log.ok(f"Saved {len(cookies)} long-lived session cookies to {COOKIES_F.name}")
        storage = context.storage_state()
        if storage:
            if "cookies" in storage and isinstance(storage["cookies"], list):
                far_future = time.time() + 31536000
                for c in storage["cookies"]:
                    if "expires" in c and (c["expires"] is None or c["expires"] < far_future):
                        c["expires"] = far_future
            STATE_F.write_text(json.dumps(storage, indent=2), encoding="utf-8")
            Log.ok(f"Saved storage_state to {STATE_F.name}")
    except Exception as e:
        Log.warn(f"Note saving session: {e}")


def login_with_google(page: Page, context: BrowserContext) -> bool:
    Log.step("GOOGLE_AUTH", "Attempting Login via Google Account OAuth...")
    init_code, init_date, _, _ = get_current_sheet_state()
    try:
        # Step 1: If we're on the SMS OTP screen, click "More options" → "Google"
        # to reach the "Continue with Google" screen
        more_opts = page.locator('button:has-text("More options"), a:has-text("More options")').first
        if more_opts.is_visible(timeout=3000):
            Log.info("On OTP screen — clicking 'More options' to reach Google login...")
            more_opts.click()
            time.sleep(2)
            # Click "Google" in the options popup
            google_option = page.locator('text="Google"').first
            if google_option.is_visible(timeout=4000):
                Log.info("Selecting 'Google' from More options...")
                google_option.click()
                time.sleep(3)

        # Step 2: Now find the "Continue with Google" button
        google_btn = page.locator('button:has-text("Continue with Google"), button:has-text("Google"), [data-testid*="google"]').first
        if not google_btn.is_visible(timeout=8000):
            Log.warn("Google button not visible even after More options — skipping OAuth")
            return False

        Log.info("Clicking 'Continue with Google' — waiting for popup window...")
        # Google OAuth opens in a NEW POPUP WINDOW — intercept it
        try:
            with context.expect_page(timeout=12000) as popup_info:
                try:
                    page.evaluate("document.querySelector('[data-testid*=\"google\"], #google-login-btn').click()")
                except Exception:
                    google_btn.click(force=True)
            gp = popup_info.value  # the Google login popup page
            gp.wait_for_load_state("domcontentloaded", timeout=15000)
            Log.ok(f"Google popup opened: {gp.url}")
        except Exception as e:
            Log.warn(f"Could not capture Google popup: {e}. Trying main page flow...")
            gp = page  # fallback: interact on main page

        time.sleep(3)

        # 1. Google Email (in popup)
        g_email = gp.locator('input[type="email"], input#identifierId').first
        if g_email.is_visible(timeout=8000):
            Log.info(f"Entering Google email: {UBER_EMAIL}")
            try:
                g_email.fill(UBER_EMAIL)
            except Exception:
                gp.keyboard.type(UBER_EMAIL, delay=30)
            time.sleep(0.5)
            next_btn = gp.locator('#identifierNext button, button:has-text("Next")').first
            try:
                if next_btn.is_visible() and next_btn.is_enabled(timeout=2000):
                    next_btn.click()
                else:
                    gp.keyboard.press("Enter")
            except Exception:
                gp.keyboard.press("Enter")
            time.sleep(5)

        # 2. Google Password — USE GMAIL_PASSWORD, not Uber portal password
        g_pwd = gp.locator('input[type="password"], input[name="Passwd"]').first
        if g_pwd.is_visible(timeout=8000):
            Log.info("Entering Google/Gmail password...")
            try:
                g_pwd.fill(GMAIL_PASSWORD)
            except Exception:
                gp.keyboard.type(GMAIL_PASSWORD, delay=30)
            time.sleep(0.5)
            next_btn = gp.locator('#passwordNext button, button:has-text("Next")').first
            try:
                if next_btn.is_visible() and next_btn.is_enabled(timeout=2000):
                    next_btn.click()
                else:
                    gp.keyboard.press("Enter")
            except Exception:
                gp.keyboard.press("Enter")
            time.sleep(6)

        # 3. Google 2FA / Phone OTP (sent to 9900092015)
        try:
            if gp and not gp.is_closed():
                content = gp.content().lower()
                if any(w in content for w in ["verification code", "2-step", "enter code", "verify", "phone"]):
                    Log.info("Google 2-Step Verification detected. Polling Google Sheet for OTP...")
                    otp = poll_for_new_otp(init_date, init_code, timeout_seconds=90)
                    if not otp:
                        otp, _, _, _ = get_current_sheet_state()
                    if otp and not gp.is_closed():
                        Log.ok(f"Entering Google 2FA OTP: {otp}")
                        otp_input = gp.locator('input#idvPin, input[type="tel"], input[name="Pin"], input[aria-label*="code"]').first
                        if otp_input.is_visible(timeout=4000):
                            otp_input.fill(otp)
                            time.sleep(0.5)
                            next_btn = gp.locator('#idvPreregisteredPhoneNext button, button:has-text("Next")').first
                            try:
                                if next_btn.is_visible() and next_btn.is_enabled(timeout=2000):
                                    next_btn.click()
                                else:
                                    gp.keyboard.press("Enter")
                            except Exception:
                                gp.keyboard.press("Enter")
                            time.sleep(6)
            else:
                Log.ok("Google popup finished and closed automatically!")
        except Exception as e:
            Log.info(f"Popup status check: {e}")

        # 4. Wait for redirect back to supplier.uber.com / fleethub.uber.com
        Log.info("Waiting for Uber portal after Google OAuth...")
        for _ in range(25):
            # If Uber shows "All set! ... Continue", click it
            try:
                all_set = page.locator('button:has-text("Continue")').first
                if all_set.is_visible(timeout=1000):
                    Log.info("Clicking 'Continue' on 'All set!' screen...")
                    all_set.click()
                    time.sleep(3)
            except Exception:
                pass

            try:
                current_urls = [p.url for p in context.pages]
                if any(("supplier.uber.com" in u or "fleethub.uber.com" in u) and "auth.uber.com" not in u and "login" not in u for u in current_urls):
                    Log.ok(f"🎉 Google OAuth Login successful! Landed on: {page.url}")
                    save_session_state(context)
                    return True
            except Exception:
                pass
            time.sleep(2)
    except Exception as e:
        Log.warn(f"Google login flow note: {e}")
    return False



def ensure_login(page: Page, context: BrowserContext) -> bool:
    time.sleep(2)
    dismiss_banner(page)

    # Bug 1 Fix: any valid supplier page (not just /orgs/) confirms active session
    if ("supplier.uber.com" in page.url or "fleethub.uber.com" in page.url) and not is_login_required(page):
        Log.ok(f"Active session confirmed on {page.url}")
        save_session_state(context)
        return True

    Log.step("AUTH", "Automated Uber Login Engine (Direct Google OAuth / Password / SMS OTP)...")

    # Only navigate to login page if currently on an auth/login page or unknown page.
    if not is_login_required(page) and "supplier.uber.com" not in page.url and "fleethub.uber.com" not in page.url:
        try:
            page.goto("https://supplier.uber.com/login", timeout=30000, wait_until="domcontentloaded")
            time.sleep(4)
            dismiss_banner(page)
        except Exception:
            pass

    # 1. Check for 'Log in' or 'Sign in' buttons on landing page
    try:
        landing_login = page.locator('a:has-text("Log in"), button:has-text("Log in"), a:has-text("Sign in"), button:has-text("Sign in")').first
        if landing_login.is_visible(timeout=3000):
            landing_login.click()
            time.sleep(4)
    except Exception:
        pass

    # =========================================================================
    # STRATEGY 1 (PRIMARY): DIRECT GOOGLE OAUTH LOGIN
    # =========================================================================
    # Uber provides 'Continue with Google' directly on the main landing screen.
    # This bypasses Uber's phone/SMS OTP flow, CAPTCHA overlays, and device challenges.
    Log.info("==> Strategy 1 (Primary): Direct Google OAuth Login...")
    try:
        if login_with_google(page, context):
            Log.ok("🎉 Strategy 1 (Direct Google OAuth) succeeded!")
            return True
    except Exception as e:
        Log.warn(f"Strategy 1 note: {e}")

    Log.warn("Strategy 1 did not complete. Falling back to Strategy 2 (Email + Password / SMS OTP)...")

    # =========================================================================
    # STRATEGY 2 (FALLBACK): STANDARD EMAIL + PASSWORD / SMS OTP
    # =========================================================================
    init_code, init_date, _, _ = get_current_sheet_state()

    try:
        email_input = page.locator('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS, input[name="textValue"]').first
        if email_input.is_visible(timeout=5000):
            Log.info(f"Entering login email: {UBER_EMAIL}")
            email_input.click()
            email_input.fill("")
            email_input.type(UBER_EMAIL, delay=30)
            # Dispatch React input, change, and blur events so validation enables the Continue button
            try:
                page.evaluate("""(val) => {
                    const el = document.querySelector('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS, input[name="textValue"]');
                    if (el) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    }
                }""", UBER_EMAIL)
            except Exception:
                pass
            time.sleep(1)

            continue_btn = page.locator('button:has-text("Continue"), button[type="submit"], button#forward-button').first
            btn_clicked = False
            try:
                if continue_btn.is_visible() and continue_btn.is_enabled(timeout=2000):
                    continue_btn.click()
                    btn_clicked = True
            except Exception:
                pass
            if not btn_clicked:
                page.keyboard.press("Enter")
            time.sleep(5)

        # Password or More Options
        pwd_inputs = page.locator('input[type="password"]')
        if pwd_inputs.count() > 0 and pwd_inputs.first.is_visible():
            Log.info("Entering password directly...")
            pwd_inputs.first.click()
            pwd_inputs.first.fill("")
            pwd_inputs.first.type(UBER_PASSWORD, delay=30)
            try:
                page.evaluate("""(val) => {
                    const el = document.querySelector('input[type="password"]');
                    if (el) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", UBER_PASSWORD)
            except Exception:
                pass
            time.sleep(1)
            submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"], button#forward-button').first
            btn_clicked = False
            try:
                if submit_btn.is_visible() and submit_btn.is_enabled(timeout=2000):
                    submit_btn.click()
                    btn_clicked = True
            except Exception:
                pass
            if not btn_clicked:
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
                        pwd_input.click()
                        pwd_input.fill("")
                        pwd_input.type(UBER_PASSWORD, delay=30)
                        try:
                            page.evaluate("""(val) => {
                                const el = document.querySelector('input[type="password"]');
                                if (el) {
                                    el.value = val;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }""", UBER_PASSWORD)
                        except Exception:
                            pass
                        time.sleep(1)
                        submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"], button#forward-button').first
                        btn_clicked = False
                        try:
                            if submit_btn.is_visible() and submit_btn.is_enabled(timeout=2000):
                                submit_btn.click()
                                btn_clicked = True
                        except Exception:
                            pass
                        if not btn_clicked:
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


def switch_to_org(context: BrowserContext, main_page: Page, org: dict, previous_orgs: set = None) -> Page:
    main_page = ensure_main_page(context, main_page)
    name = org["name"]
    org_uuid = org["uuid"]
    city = org["city"]

    Log.step("SWITCH", f"Opening {name} ({city})")

    # 1. Direct URL navigation if org_uuid is known (fast & reliable)
    if org_uuid:
        url = f"https://supplier.uber.com/orgs/{org_uuid}/promotions"
        Log.info(f"Direct navigating to {name} URL: {url}...")
        try:
            main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
            Log.wait(3, f"Loading promotions page for {name}")
            main_page = ensure_main_page(context, main_page)
            dismiss_banner(main_page)

            # Check if redirected to auth
            if is_login_required(main_page):
                Log.warn(f"Login required (detected URL: {main_page.url})! Triggering automated login...")
                if ensure_login(main_page, context):
                    main_page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    time.sleep(3)
                    dismiss_banner(main_page)

            if f"/orgs/{org_uuid}" in main_page.url:
                Log.ok(f"✅ Direct URL verified for {name} ({org_uuid})")
                return main_page
            else:
                Log.warn(f"URL did not contain target org {org_uuid} — falling through to UI Switcher.")
        except Exception as e:
            Log.warn(f"Direct navigation note: {e}")
            main_page = ensure_main_page(context, main_page)

    # 2. UI Switcher Navigation using exact data-testid="org-select-{org_uuid}"
    for attempt in range(1, 3):
        Log.info(f"Attempt {attempt}/2: Opening Account Switcher UI for {name}...")
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

            # Click by exact testid
            switch_result = main_page.evaluate("""(targetUuid) => {
                const allDivs = Array.from(document.querySelectorAll('div, ul, section'));
                const containers = allDivs.filter(el => {
                    const s = window.getComputedStyle(el);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                });
                const container = containers[containers.length - 1];

                const findAndClick = () => {
                    const el = document.querySelector('[data-testid="org-select-' + targetUuid + '"]');
                    if (el) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        el.click();
                        return true;
                    }
                    return false;
                };

                if (findAndClick()) return { success: true };

                if (container) {
                    for (let pos = 50; pos <= container.scrollHeight; pos += 50) {
                        container.scrollTop = pos;
                        if (findAndClick()) return { success: true };
                    }
                }
                return { success: false };
            }""", org_uuid)

            if switch_result.get("success"):
                Log.ok(f"Switcher clicked org item: {org_uuid}")
                time.sleep(4)
                main_page = ensure_main_page(context, main_page)
                dismiss_banner(main_page)
                return main_page

        except Exception as e:
            Log.warn(f"Switcher attempt {attempt} note: {e}")
            time.sleep(2)

    # Fallback: direct goto promotions page
    main_page.goto(f"https://supplier.uber.com/orgs/{org_uuid}/promotions", timeout=30000)
    return main_page


def switch_to_city(context: BrowserContext, main_page: Page, target: dict, previous_orgs: set) -> Page:
    """Backwards-compatibility wrapper for switch_to_org."""
    org = {
        "name": target.get("account_name", target.get("city", "Unknown")),
        "uuid": target.get("org_uuid", ""),
        "city": target.get("city", "Unknown"),
        "slug": target.get("file_keyword", target.get("code", "ORG"))
    }
    return switch_to_org(context, main_page, org, previous_orgs)


def export_and_download_org(context: BrowserContext, main_page: Page, org: dict, download_state: dict, seen_files: set = None) -> Path:
    main_page = ensure_main_page(context, main_page)
    name = org["name"]
    uuid = org["uuid"]
    city = org["city"]
    slug = org.get("slug") or re.sub(r'[^A-Za-z0-9_]+', '_', name).strip('_')
    max_wait = org.get("max_wait_seconds", 600)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist_tz).strftime("%Y%m%d")

    Log.step("EXPORT", f"Triggering Export for {name} ({city})")
    dismiss_banner(main_page)

    # Allow 20-25s for DOM hydration & Export button to render as requested
    exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
    try:
        exp_btn.wait_for(state="visible", timeout=25000)
    except Exception:
        pass

    if not exp_btn.is_visible(timeout=3000):
        # Perform 1 clean refresh and wait another 20s
        Log.info(f"Export button not visible immediately for {name}. Refreshing to hydrate DOM...")
        try:
            main_page.reload(wait_until="domcontentloaded", timeout=30000)
            dismiss_banner(main_page)
            exp_btn = main_page.locator('[data-testid="promotions-export-button"], button:has-text("Export")').first
            exp_btn.wait_for(state="visible", timeout=20000)
        except Exception:
            pass

    if not exp_btn.is_visible(timeout=2000):
        Log.warn(f"Export button not visible on {name} Promotions page after 25s wait! (URL: {main_page.url})")
        return None

    if seen_files is None:
        seen_files = set()

    download_state["latest_file"] = None
    trigger_time = time.time()
    Log.info(f"Clicking 'Export' button for {name}...")
    try:
        exp_btn.scroll_into_view_if_needed(timeout=5000)
        exp_btn.click(timeout=8000)
    except Exception:
        try:
            exp_btn.evaluate("b => b.click()")
        except Exception:
            exp_btn.click(force=True)

    Log.ok(f"Export triggered for {name}! Monitoring download (up to {max_wait//60} mins)...")

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

        # 2. Scan OUT_DIR and USER_DL_DIR
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
                        # Strict trigger_time check with 3s drift tolerance
                        if f.stat().st_mtime >= (trigger_time - 3.0) and f.stat().st_size > 100:
                            if is_valid_incentive_file(f):
                                dest = OUT_DIR / f"{today}-vehicle_incentives-{slug}.csv"
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
            Log.info(f"Still waiting on Uber export for {name}... ({mins}m {secs}s / {max_wait//60}m)")

        time.sleep(2)

    # Safe to close popup tabs
    time.sleep(2)
    close_popup_tabs(context, main_page)

    if found_file and found_file.exists():
        dest_csv  = OUT_DIR / f"{today}-vehicle_incentives-{slug}.csv"
        dest_xlsx = OUT_DIR / f"{today}-vehicle_incentives-{slug}.xlsx"

        if found_file != dest_csv:
            shutil.copy2(str(found_file), str(dest_csv))
        seen_files.add(str(dest_csv))

        try:
            df = pd.read_csv(dest_csv, encoding="utf-8-sig", low_memory=False, dtype=str)
            df["City"] = city
            df["org_name"] = name
            df["org_uuid"] = uuid
            df.to_excel(dest_xlsx, index=False)
            sample_plates = df["Number plate"].dropna().head(3).tolist() if "Number plate" in df.columns else []
            Log.ok(f"✅ Saved official dataset ({len(df):,} rows) -> {dest_xlsx.name}")
            Log.info(f"🔍 Sample plates for {name}: {sample_plates}")
            return dest_csv
        except Exception as e:
            Log.err(f"CSV read/Excel conversion failed for {name}: {e} — treating as failed export.")
            return None

    Log.warn(f"Timed out after {max_wait}s waiting for {name} export.")
    return None


def export_and_download_city(context: BrowserContext, main_page: Page, target: dict, download_state: dict, seen_files: set = None) -> Path:
    """Backwards-compatibility wrapper for export_and_download_org."""
    org = {
        "name": target.get("account_name", target.get("city", "Unknown")),
        "uuid": target.get("org_uuid", ""),
        "city": target.get("city", "Unknown"),
        "slug": target.get("file_keyword", target.get("code", "ORG")),
        "max_wait_seconds": target.get("max_wait_seconds", 600)
    }
    return export_and_download_org(context, main_page, org, download_state, seen_files)


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
    print("   LETZRYD - UBER OFFICIAL EXPORT ENGINE (ALL FLEET SUB-ORGS)")
    print("   Dynamic Discovery & Universal Multi-Org Extraction")
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

            # Pre-flight session check
            if not verify_session_active(main_page):
                Log.warn("Session cookies expired or invalid. Purging stale cookies and triggering automated login now...")
                try:
                    context.clear_cookies()
                except Exception:
                    pass
                if not ensure_login(main_page, context):
                    raise RuntimeError("Pre-flight login failed. Cannot proceed without authenticated session.")

            # Dynamic Discovery of ALL Sub-Orgs
            all_orgs = discover_available_orgs(main_page)
            if not all_orgs:
                raise RuntimeError("Failed to discover any Uber fleet orgs to process.")

            Log.ok(f"🚀 Processing {len(all_orgs)} total sub-accounts/sub-orgs...")

            all_city_dfs = []
            ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            today = datetime.datetime.now(ist_tz).strftime("%Y%m%d")
            seen_files: set = set()
            previous_orgs: set = set()

            for i, org in enumerate(all_orgs):
                org_name = org["name"]
                uuid = org["uuid"]
                city = org["city"]
                print(f"\n[{i+1}/{len(all_orgs)}] >>> Processing: {org_name} ({city}) <<<")

                try:
                    main_page = switch_to_org(context, main_page, org, previous_orgs)
                    time.sleep(1)

                    # 1 Clean page refresh + DOM stabilization
                    Log.info(f"Performing clean page refresh for {org_name}...")
                    try:
                        main_page.reload(wait_until="domcontentloaded", timeout=30000)
                        Log.wait(3, "Stabilizing page")
                        dismiss_banner(main_page)

                        if is_login_required(main_page):
                            Log.warn(f"Session dropped during {org_name} reload! Re-logging in...")
                            if ensure_login(main_page, context):
                                main_page.goto(f"https://supplier.uber.com/orgs/{uuid}/promotions",
                                               timeout=30000, wait_until="domcontentloaded")
                                time.sleep(3)
                    except Exception as e:
                        Log.warn(f"  Refresh note: {e}")
                        time.sleep(2)

                    download_state["latest_file"] = None
                    original_main_page = main_page
                    csv_path = export_and_download_org(context, main_page, org, download_state, seen_files)
                    main_page = ensure_main_page(context, original_main_page)

                    if csv_path and csv_path.exists():
                        try:
                            df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False, dtype=str)
                            df["City"] = city
                            df["org_name"] = org_name
                            df["org_uuid"] = uuid
                            all_city_dfs.append(df)
                            Log.ok(f"✅ {org_name} ({city}): {len(df):,} rows collected.")
                            previous_orgs.add(uuid)
                        except Exception as e:
                            Log.err(f"Failed to read CSV for {org_name}: {e} — skipping this org.")
                    else:
                        Log.warn(f"No CSV collected for {org_name} (skipped or empty).")

                except Exception as e:
                    Log.err(f"Org {org_name} encountered error: {e}. Continuing with remaining orgs...")
                    try:
                        main_page = ensure_main_page(context, main_page)
                    except Exception:
                        pass

                # Short 2s cooldown between orgs
                if i < len(all_orgs) - 1:
                    time.sleep(2)

            if all_city_dfs:
                master_df = pd.concat(all_city_dfs, ignore_index=True)
                
                # Standard Master filenames
                master_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx"
                master_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.csv"
                master_all_xlsx = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_ORGS.xlsx"
                master_all_csv  = OUT_DIR / f"{today}-vehicle_incentives-SAMVREEDDHI_ALL_ORGS.csv"

                # Ensure priority columns: City, org_name, org_uuid
                priority_cols = ["City", "org_name", "org_uuid"]
                other_cols = [c for c in master_df.columns if c not in priority_cols]
                master_df = master_df[priority_cols + other_cols]

                master_df.to_excel(master_xlsx, index=False)
                master_df.to_csv(master_csv, index=False)
                shutil.copy2(str(master_xlsx), str(master_all_xlsx))
                shutil.copy2(str(master_csv), str(master_all_csv))

                Log.ok("=" * 70)
                Log.ok(f"🎉 MASTER CONSOLIDATED REPORT GENERATED SUCCESSFULLY!")
                Log.ok(f"📁 Excel: {master_xlsx}")
                Log.ok(f"📊 Total Rows Across All Discovered Orgs: {len(master_df):,}")
                Log.ok("=" * 70)

        finally:
            Log.info("Closing browser context cleanly...")
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
