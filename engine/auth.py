"""Authentication helper script to generate and serialize Facebook session cookies."""

import os
import sys
import json
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("FacebookSnoof.Auth")

STORAGE_STATE_PATH = "config/storage_state.json"


def generate_interactive_session() -> None:
    """Launch non-headless Playwright Chromium for interactive user login and serialize session state."""
    os.makedirs("config", exist_ok=True)
    logger.info("Starting interactive browser session for manual Facebook login...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        logger.info("Navigating to Facebook login page...")
        page.goto("https://www.facebook.com/")
        
        print("\n" + "=" * 70)
        print("INSTRUCTIONS FOR USER:")
        print("1. Log in manually to your Facebook account in the opened browser window.")
        print("2. Complete any 2FA or identity security prompts if requested by Facebook.")
        print("3. Once logged in and viewing the main news feed, return here and press [ENTER].")
        print("=" * 70 + "\n")
        
        input("Press [ENTER] after completing manual login in the browser window: ")
        
        context.storage_state(path=STORAGE_STATE_PATH)
        logger.info(f"Session cookies and state saved successfully to: {STORAGE_STATE_PATH}")
        browser.close()


def validate_storage_state(path: str = STORAGE_STATE_PATH) -> bool:
    """Validate whether the storage_state.json file exists and contains valid cookie keys."""
    if not os.path.exists(path):
        logger.warning(f"Storage state file not found at: {path}")
        return False
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cookies = data.get("cookies", [])
            cookie_names = {c.get("name") for c in cookies}
            
            # Check for critical Facebook authentication cookies
            if "c_user" in cookie_names and "xs" in cookie_names:
                logger.info("Valid Facebook session cookies (c_user, xs) detected.")
                return True
            else:
                logger.warning("Storage state exists but is missing critical session cookies (c_user, xs).")
                return False
    except Exception as e:
        logger.error(f"Failed to read or parse storage state file: {e}")
        return False


if __name__ == "__main__":
    generate_interactive_session()
