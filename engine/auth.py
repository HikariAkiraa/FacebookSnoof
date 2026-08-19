"""Authentication helper script to generate and serialize Facebook session cookies."""

import os
import sys
import re
import time
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


def update_storage_state_from_cookie_string(cookie_input: str, storage_state_path: str = STORAGE_STATE_PATH) -> bool:
    """Parse cookie string containing c_user and xs (from mobile/browser bookmarklet) and construct a Playwright storage_state.json valid for 2 years."""
    import time
    c_user_match = re.search(r"c_user=([^\s;]+)", cookie_input)
    xs_match = re.search(r"xs=([^\s;]+)", cookie_input)

    if not c_user_match or not xs_match:
        logger.error("Failed to parse critical Facebook cookies (c_user, xs) from input string.")
        return False

    c_user_val = c_user_match.group(1)
    xs_val = xs_match.group(1)

    datr_match = re.search(r"datr=([^\s;]+)", cookie_input)
    fr_match = re.search(r"fr=([^\s;]+)", cookie_input)
    sb_match = re.search(r"sb=([^\s;]+)", cookie_input)

    expires_timestamp = int(time.time()) + 63072000  # 2 years in future

    cookies = [
        {
            "name": "c_user",
            "value": c_user_val,
            "domain": ".facebook.com",
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None"
        },
        {
            "name": "xs",
            "value": xs_val,
            "domain": ".facebook.com",
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }
    ]

    if datr_match:
        cookies.append({
            "name": "datr",
            "value": datr_match.group(1),
            "domain": ".facebook.com",
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        })

    if fr_match:
        cookies.append({
            "name": "fr",
            "value": fr_match.group(1),
            "domain": ".facebook.com",
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        })

    if sb_match:
        cookies.append({
            "name": "sb",
            "value": sb_match.group(1),
            "domain": ".facebook.com",
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        })

    storage_state_data = {
        "cookies": cookies,
        "origins": [
            {
                "origin": "https://www.facebook.com",
                "localStorage": []
            }
        ]
    }

    os.makedirs(os.path.dirname(storage_state_path) if os.path.dirname(storage_state_path) else ".", exist_ok=True)
    with open(storage_state_path, "w", encoding="utf-8") as f:
        json.dump(storage_state_data, f, indent=2)

    logger.info(f"Successfully generated new Facebook storage_state.json valid for 2 years at: {storage_state_path}")
    return True


if __name__ == "__main__":
    import re
    if len(sys.argv) > 1:
        raw_cookie_input = " ".join(sys.argv[1:])
        logger.info("Updating Facebook session cookies from command line string...")
        success = update_storage_state_from_cookie_string(raw_cookie_input)
        if success:
            print("\n✅ SUCCESS: Facebook session cookies updated successfully for 2 years!")
        else:
            print("\n❌ ERROR: Failed to parse c_user and xs cookies from input string.")
    else:
        generate_interactive_session()
