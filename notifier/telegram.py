"""Telegram Bot API notification client for FacebookSnoof deal alerts."""

import logging
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger("FacebookSnoof.Notifier")


class TelegramNotifier:
    """Dispatches formatted Markdown alerts to Telegram channels or private chats."""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def format_deal_message(
        self,
        hardware_name: str,
        asking_price: int,
        estimated_market_price: int,
        deal_score: int,
        verdict: str,
        condition: str,
        reasoning: str,
        post_url: str,
        group_name: str = "FB Group"
    ) -> str:
        """Format deal valuation data into structured Markdown message for Telegram."""
        savings = estimated_market_price - asking_price
        discount_pct = (savings / estimated_market_price * 100) if estimated_market_price > 0 else 0

        # Score emoji indicator
        score_emoji = "🔥" if deal_score >= 85 else "✨" if deal_score >= 75 else "⚠️"

        msg = (
            f"{score_emoji} *DEAL ALERT: {hardware_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Asking Price:* Rp {asking_price:,}\n"
            f"📊 *Estimated Market:* Rp {estimated_market_price:,}\n"
            f"💰 *Potential Savings:* Rp {savings:,} ({discount_pct:.1f}% OFF)\n"
            f"⭐ *Deal Score:* `{deal_score}/100` ({verdict})\n\n"
            f"🔍 *Condition:* {condition}\n"
            f"💡 *Reasoning:* _{reasoning}_\n\n"
            f"📍 *Group:* {group_name}\n"
            f"🔗 [View Original Facebook Post]({post_url})"
        )
        return msg

    def send_deal_alert(
        self,
        hardware_name: str,
        asking_price: int,
        estimated_market_price: int,
        deal_score: int,
        verdict: str,
        condition: str,
        reasoning: str,
        post_url: str,
        group_name: str = "FB Group"
    ) -> bool:
        """Send formatted deal alert to Telegram."""
        if not self.enabled:
            logger.info("Telegram notification is disabled in configuration. Skipping send.")
            return False

        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram Bot Token is not configured. Skipping alert.")
            return False

        message = self.format_deal_message(
            hardware_name=hardware_name,
            asking_price=asking_price,
            estimated_market_price=estimated_market_price,
            deal_score=deal_score,
            verdict=verdict,
            condition=condition,
            reasoning=reasoning,
            post_url=post_url,
            group_name=group_name
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }

        try:
            logger.info(f"Sending Telegram deal alert for [{hardware_name}] (Score: {deal_score})...")
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.api_url, json=payload)
                response.raise_for_status()
                logger.info("Telegram alert sent successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
