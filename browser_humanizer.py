import os
import sys
import time
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "uber_chrome_profile")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def cleanup_chrome_locks():
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(PROFILE_DIR, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass

def human_type(locator, text):
    """Simulate human typing with randomized delays."""
    locator.click()
    time.sleep(random.uniform(0.2, 0.5))
    locator.fill("")
    for char in text:
        locator.type(char, delay=random.uniform(40, 110))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.1, 0.25))

def human_click(page, locator):
    """Simulate human mouse hover and click."""
    box = locator.bounding_box()
    if box:
        # Move mouse near center with slight offset
        x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
        y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        page.mouse.move(x, y, steps=random.randint(5, 12))
        time.sleep(random.uniform(0.15, 0.35))
        page.mouse.click(x, y)
    else:
        locator.click()

def apply_stealth_and_fingerprints(page):
    """Injects evasions and realistic device properties."""
    stealth_sync(page)
    
    # Overwrite navigator.webdriver and common automation signatures
    page.add_init_script("""
        // Hide webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Mock Chrome runtime
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Realistic hardware specs
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-GB', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

        // WebGL vendor/renderer spoofing (Real desktop GPU)
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Google Inc. (NVIDIA)';
            }
            if (parameter === 37446) {
                return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            }
            return getParameter.apply(this, arguments);
        };
    """)

def launch_humanized_browser(p):
    cleanup_chrome_locks()
    
    # Modern real Chrome User-Agent
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        channel="chrome",
        headless=False,
        user_agent=user_agent,
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        geolocation={"latitude": 12.9716, "longitude": 77.5946},
        permissions=["geolocation"],
        viewport={"width": 1440, "height": 900},
        screen={"width": 1920, "height": 1080},
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-default-browser-check",
            "--start-maximized",
            "--disable-features=IsolateOrigins,site-per-process",
            "--lang=en-IN,en"
        ]
    )
    return context
