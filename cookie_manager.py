import os
import json
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "storage_state.json")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.json")

def save_session_state(context):
    """Saves all browser cookies, session tokens, and local storage."""
    try:
        context.storage_state(path=STATE_FILE)
        cookies = context.cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {len(cookies)} session cookies to {COOKIES_FILE}")
        return True
    except Exception as e:
        print(f"Warning saving cookies: {e}")
        return False

def load_session_cookies(context):
    """Loads saved cookies into browser context if available."""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Restored {len(cookies)} cookies from cache.")
            return True
        except Exception as e:
            print(f"Warning loading cookies: {e}")
    return False
