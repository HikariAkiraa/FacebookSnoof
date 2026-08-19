"""Playwright Stealth Collector with GraphQL interception and DOM hybrid fallback parsing."""

import os
import re
import json
import time
import random
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
try:
    from playwright.sync_api import sync_playwright, Page, Response, BrowserContext
except ImportError:
    sync_playwright, Page, Response, BrowserContext = None, None, None, None


logger = logging.getLogger("FacebookSnoof.Collector")


class FacebookCollector:
    """Scrapes chronological listings from Facebook Groups using Playwright network interception and DOM fallback."""

    def __init__(
        self,
        storage_state_path: str = "config/storage_state.json",
        headless: bool = True,
        max_scrolls: int = 4,
        delay_min: float = 5.0,
        delay_max: float = 12.0
    ):
        self.storage_state_path = storage_state_path
        self.headless = headless
        self.max_scrolls = max_scrolls
        self.delay_min = delay_min
        self.delay_max = delay_max
        os.makedirs("logs", exist_ok=True)

    def _apply_stealth_scripts(self, context: BrowserContext) -> None:
        """Inject anti-detection evasions to mask Playwright automation flags."""
        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """
        context.add_init_script(stealth_js)

    def _random_delay(self) -> None:
        """Sleep for a randomized jitter delay to simulate human pause."""
        sleep_time = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"Humanized pause: sleeping for {sleep_time:.2f} seconds...")
        time.sleep(sleep_time)

    def _extract_post_id_from_url(self, url: str) -> Optional[str]:
        """Extract numeric or alphanumeric post ID from Facebook URL permalink."""
        match = re.search(r"/(?:posts|permalink|multi_permalink)/(\d+)", url)
        if match:
            return match.group(1)
        match_pfbid = re.search(r"/(pfbid[a-zA-Z0-9]+)", url)
        if match_pfbid:
            return match_pfbid.group(1)
        return None

    def scrape_group(self, group_id: str, group_name: str, discord_notifier: Any = None) -> List[Dict[str, Any]]:
        """Scrape chronological posts for a specified Facebook Group ID."""
        if sync_playwright is None:
            logger.error("Playwright package is not installed. Please run `pip install playwright && playwright install chromium`.")
            return []

        target_url = f"https://www.facebook.com/groups/{group_id}/?sorting_setting=CHRONOLOGICAL"
        extracted_posts: List[Dict[str, Any]] = []
        graphql_captured_texts: List[str] = []

        if not os.path.exists(self.storage_state_path):
            logger.error(f"Storage state file missing at: {self.storage_state_path}. Please generate cookies first.")
            if discord_notifier:
                discord_notifier.send_session_expired_alert("Storage state cookie file missing!")
            return []

        logger.info(f"Navigating to group [{group_name}] (ID: {group_id})...")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars"
                ]
            )

            context = browser.new_context(
                storage_state=self.storage_state_path,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": random.randint(1280, 1440), "height": random.randint(800, 900)}
            )

            self._apply_stealth_scripts(context)
            page = context.new_page()

            # Network Interception Strategy for GraphQL payloads
            def handle_response(response: Response):
                if "/api/graphql/" in response.url and response.status == 200:
                    try:
                        text = response.text()
                        if "message" in text or "story" in text or "comet_sections" in text:
                            graphql_captured_texts.append(text)
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                self._random_delay()

                # Check if Facebook redirected to login screen, checkpoint, or landing page
                current_url = page.url.lower()
                if "login" in current_url or "checkpoint" in current_url or "/groups/" not in current_url:
                    logger.error(f"Facebook session expired or redirected to login screen ({page.url}). Cookies in storage_state.json may have expired! Please re-run `python engine/auth.py` or use /setcookie.")
                    if discord_notifier:
                        discord_notifier.send_session_expired_alert(page.url)
                    return []

                # Wait for React feed component to mount
                try:
                    page.wait_for_selector('div[role="feed"], div[role="main"], div[data-pagelet^="FeedUnit"]', timeout=10000)
                except Exception:
                    pass

                # Perform scroll iterations
                for scroll_step in range(self.max_scrolls):
                    logger.info(f"Scrolling group [{group_name}] (Step {scroll_step + 1}/{self.max_scrolls})...")
                    page.evaluate("window.scrollBy(0, random_scroll = Math.floor(Math.random() * 600) + 400);")
                    page.keyboard.press("PageDown")
                    self._random_delay()

                # Primary Strategy: Parse intercepted GraphQL payloads
                if graphql_captured_texts:
                    logger.info(f"Processing {len(graphql_captured_texts)} intercepted GraphQL network streams...")
                    for raw_json_str in graphql_captured_texts:
                        extracted_posts.extend(self._parse_graphql_payload(raw_json_str, group_id))

                # Secondary Strategy: DOM Fallback Parser if GraphQL yields zero posts
                if not extracted_posts:
                    logger.warning("Primary GraphQL interception yielded 0 items. Triggering DOM Hybrid Fallback Parser...")
                    html_content = page.content()
                    extracted_posts = self._parse_dom_fallback(html_content, group_id)

                # Diagnostic Dump if both strategies fail
                if not extracted_posts:
                    logger.error(f"Both extraction strategies failed for group {group_id}. Dumping debug snapshot to logs/debug_feed.html.")
                    with open("logs/debug_feed.html", "w", encoding="utf-8") as f:
                        f.write(page.content())

            except Exception as e:
                logger.error(f"Error during collection of group {group_id}: {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        logger.info(f"Extracted {len(extracted_posts)} total raw posts from group [{group_name}].")
        return extracted_posts

    def _parse_graphql_payload(self, raw_json_str: str, group_id: str) -> List[Dict[str, Any]]:
        """Parse raw GraphQL batch payload strings for post text and permalinks."""
        posts = []
        try:
            # Handle newline-delimited JSON payloads
            lines = raw_json_str.strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    text_matches = re.findall(r'"text"\s*:\s*"([^"]{20,})"', line)
                    url_matches = re.findall(r'https:\\/\\/www\.facebook\.com\\/groups\\/[0-9]+\\/posts\\/([0-9]+)', line)
                    
                    for text in text_matches:
                        clean_text = text.encode().decode('unicode_escape', errors='ignore')
                        post_id = str(hash(clean_text[:50])) if not url_matches else url_matches[0]
                        post_url = f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"
                        posts.append({
                            "post_id": post_id,
                            "group_id": group_id,
                            "post_text": clean_text,
                            "post_url": post_url,
                            "author_name": "Facebook User"
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Failed parsing GraphQL batch segment: {e}")
        return posts

    def _parse_dom_fallback(self, html_content: str, group_id: str) -> List[Dict[str, Any]]:
        """DOM Fallback parser using BeautifulSoup to extract individual post articles with verified permalinks."""
        posts = []
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Strategy 1: Find candidate containers via role="article" or data-pagelet FeedUnit
        candidate_containers = soup.find_all(lambda tag: tag.name == "div" and (
            tag.get("role") == "article" or
            (tag.get("data-pagelet") and "FeedUnit" in str(tag.get("data-pagelet")))
        ))

        # Strategy 2: Search for all post permalink anchor tags and find their parent wrappers
        permalink_anchors = soup.find_all("a", href=lambda href: href and self._extract_post_id_from_url(href) is not None)
        seen_parents = {id(c) for c in candidate_containers}
        
        for a in permalink_anchors:
            parent = (
                a.find_parent("div", attrs={"role": "article"}) or
                a.find_parent("div", attrs={"data-pagelet": re.compile(r"FeedUnit", re.I)}) or
                a.find_parent("div", attrs={"dir": "auto"}) or
                a.parent
            )
            if parent and id(parent) not in seen_parents:
                seen_parents.add(id(parent))
                candidate_containers.append(parent)

        logger.info(f"DOM Fallback found {len(candidate_containers)} candidate post containers.")

        seen_post_ids = set()
        for idx, container in enumerate(candidate_containers):
            # Extract verified permalink link inside this specific article container
            links = container.find_all("a", href=True)
            post_url = ""
            post_id = ""
            for a in links:
                href = a["href"]
                extracted_id = self._extract_post_id_from_url(href)
                if extracted_id:
                    post_id = extracted_id
                    post_url = f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"
                    break

            # STRICT RULE: Discard container if no verified post permalink ID was found
            if not post_id or post_id in seen_post_ids:
                continue

            # Extract clean post text specific to this article
            # Target post text elements (div[dir="auto"] or message blocks)
            text_blocks = container.find_all("div", attrs={"dir": "auto"})
            if text_blocks:
                text_content = " ".join([block.get_text(separator=" ", strip=True) for block in text_blocks if len(block.get_text()) > 10])
            else:
                text_content = container.get_text(separator=" ", strip=True)

            if len(text_content.strip()) < 15:
                continue

            seen_post_ids.add(post_id)
            posts.append({
                "post_id": post_id,
                "group_id": group_id,
                "post_text": text_content,
                "post_url": post_url,
                "author_name": "Facebook User"
            })
            
        return posts
