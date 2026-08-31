import os
import sys
import time
from playwright.sync_api import sync_playwright
from browser_humanizer import launch_humanized_browser, apply_stealth_and_fingerprints, human_type, human_click

EMAIL = "uber.india@letzryd.com"
PASSWORD = "Letzuberp123"
START_URL = "https://supplier.uber.com/orgs/e8cf5236-6308-4631-a12c-1969c8da16c7/reports"

def run_setup():
    print("=======================================================")
    print("   UBER PERSISTENT BROWSER SESSION SETUP & HUMANIZER   ")
    print("=======================================================")
    print("This will open a real Chrome browser with human fingerprints.")
    print("Once logged in, Uber marks this browser profile as a 'TRUSTED DEVICE'.")
    print("Subsequent automated runs will not require OTP/verification.\n")
    
    with sync_playwright() as p:
        context = launch_humanized_browser(p)
        page = context.pages[0] if context.pages else context.new_page()
        apply_stealth_and_fingerprints(page)
        
        print(f"Navigating to {START_URL}...")
        page.goto(START_URL, timeout=45000)
        page.wait_for_timeout(3000)

        # Automated attempt with humanized interaction
        if "auth.uber.com" in page.url:
            print("Entering email with human typing simulation...")
            try:
                email_input = page.locator('input[type="text"], input[type="email"], input#PHONE_NUMBER_OR_EMAIL_ADDRESS').first
                if email_input.is_visible(timeout=5000):
                    human_type(email_input, EMAIL)
                    time.sleep(0.5)
                    continue_btn = page.locator('button:has-text("Continue"), button[type="submit"]').first
                    if continue_btn.is_visible():
                        human_click(page, continue_btn)
                    page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Email note: {e}")

            # More options -> See all options -> Password
            try:
                more_opts = page.get_by_text("More options", exact=False).first
                if more_opts.is_visible(timeout=3000):
                    human_click(page, more_opts)
                    page.wait_for_timeout(1500)
                    
                    see_all = page.get_by_text("See all options", exact=False).first
                    if see_all.is_visible(timeout=2000):
                        human_click(page, see_all)
                        page.wait_for_timeout(1500)

                    pwd_opt = page.get_by_text("Password", exact=True).first
                    if not pwd_opt.is_visible(timeout=1500):
                        pwd_opt = page.locator('div[role="dialog"] >> text="Password"').first
                        
                    if pwd_opt.is_visible(timeout=3000):
                        human_click(page, pwd_opt)
                        page.wait_for_timeout(2000)
                        
                        pwd_input = page.locator('input[type="password"]').first
                        if pwd_input.is_visible(timeout=4000):
                            print("Entering password with human keystroke variation...")
                            human_type(pwd_input, PASSWORD)
                            time.sleep(0.5)
                            submit_btn = page.locator('button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]').first
                            if submit_btn.is_visible():
                                human_click(page, submit_btn)
                            page.wait_for_timeout(4000)
            except Exception as e:
                print(f"Password step note: {e}")

        print("\n-------------------------------------------------------------")
        print("Browser window is open. You can view or interact with it.")
        print("Waiting until Supplier Portal is loaded...")
        print("-------------------------------------------------------------")

        # Monitor until supplier portal is active
        max_wait = 180
        start = time.time()
        while time.time() - start < max_wait:
            if "supplier.uber.com" in page.url and "auth.uber.com" not in page.url:
                print("\n SUCCESS! Logged into Uber Supplier Portal!")
                print(f"Active URL: {page.url}")
                print("Session cookies and Device Fingerprint have been permanently saved.")
                print("You can now run 'uber_incentive_scraper.py' directly without login hurdles!")
                break
            time.sleep(2)

        time.sleep(5)
        context.close()

if __name__ == "__main__":
    run_setup()
