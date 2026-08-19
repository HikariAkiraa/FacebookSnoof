"""Discord Webhook notification client for FacebookSnoof deal alerts and phase-2 skipped summaries."""

import logging
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger("FacebookSnoof.DiscordNotifier")


class DiscordNotifier:
    """Dispatches formatted Discord Embed alerts to Discord channels via Webhook."""

    def __init__(self, webhook_url: str, enabled: bool = True):
        self.webhook_url = webhook_url.strip().rstrip("/") if webhook_url else ""
        self.enabled = enabled

    def format_deal_embed_payload(
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
    ) -> Dict[str, Any]:
        """Construct a high-priority 'WAW' Discord Embed for high-score deals (Gold / Emerald Green)."""
        savings = estimated_market_price - asking_price
        discount_pct = (savings / estimated_market_price * 100) if estimated_market_price > 0 else 0

        # Gold (0xFFD700) for Score >= 85, Emerald Green (0x00FF7F) for Score >= 75
        embed_color = 0xFFD700 if deal_score >= 85 else 0x00FF7F

        embed = {
            "title": f"🔥 [HOT DEAL ALERT] {hardware_name}",
            "url": post_url,
            "description": f"**💡 Alasan Penilaian:**\n_{reasoning}_\n\n🔗 [**KLIK DISINI UNTUK BUKA POSTINGAN FACEBOOK**]({post_url})",
            "color": embed_color,
            "fields": [
                {
                    "name": "🏷️ Harga Penjual",
                    "value": f"**Rp {asking_price:,}**",
                    "inline": True
                },
                {
                    "name": "📊 Estimasi Harga Pasar",
                    "value": f"Rp {estimated_market_price:,}",
                    "inline": True
                },
                {
                    "name": "💰 Potensi Hemat",
                    "value": f"**Rp {savings:,}** ({discount_pct:.1f}% OFF)",
                    "inline": True
                },
                {
                    "name": "⭐ Skor Deal",
                    "value": f"**`{deal_score}/100`** ({verdict})",
                    "inline": True
                },
                {
                    "name": "🔍 Kondisi Unit",
                    "value": condition if condition else "Normal",
                    "inline": True
                },
                {
                    "name": "📍 Grup Facebook",
                    "value": group_name,
                    "inline": True
                }
            ],
            "footer": {
                "text": "⚡ FacebookSnoof Autonomous Deal Finder • High-Priority Alert"
            }
        }

        return {
            "username": "🔥 FacebookSnoof DEAL HUNTER",
            "embeds": [embed]
        }

    def format_skipped_embed_payload(
        self,
        hardware_name: str,
        asking_price: int,
        estimated_market_price: int,
        deal_score: int,
        verdict: str,
        reasoning: str,
        post_url: str,
        group_name: str = "FB Group",
        is_valid_pc_hardware: bool = True
    ) -> Dict[str, Any]:
        """Construct a subtle grey Discord Embed for Phase-1 passed posts that were skipped in Phase 2."""
        embed_color = 0x7F8C8D  # Muted Slate Grey

        if is_valid_pc_hardware:
            price_detail = f"Rp {asking_price:,} (Pasar: Rp {estimated_market_price:,} | Skor: {deal_score}/100)"
        else:
            price_detail = f"Rp {asking_price:,} | Non-PC Hardware Core"

        embed = {
            "title": f"⚠️ [SKIPPED IN PHASE 2] {hardware_name}",
            "url": post_url,
            "description": f"**💡 Alasan Skip:**\n_{reasoning}_",
            "color": embed_color,
            "fields": [
                {
                    "name": "🏷️ Status & Harga",
                    "value": price_detail,
                    "inline": True
                },
                {
                    "name": "📍 Grup Facebook",
                    "value": group_name,
                    "inline": True
                },
                {
                    "name": "🔗 Permalink",
                    "value": f"[Buka Link Post Facebook]({post_url})",
                    "inline": False
                }
            ],
            "footer": {
                "text": "FacebookSnoof Market Monitor • Phase 2 Skipped Info"
            }
        }

        return {
            "username": "FacebookSnoof Monitor",
            "embeds": [embed]
        }

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
        """Send high-priority 'WAW' Discord Embed alert for high-score deals."""
        if not self.enabled or not self.webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in self.webhook_url:
            return False

        payload = self.format_deal_embed_payload(
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

        try:
            logger.info(f"Sending WAW Discord Deal alert for [{hardware_name}] (Score: {deal_score})...")
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Discord deal alert: {e}")
            return False

    def send_skipped_alert(
        self,
        hardware_name: str,
        asking_price: int,
        estimated_market_price: int,
        deal_score: int,
        verdict: str,
        reasoning: str,
        post_url: str,
        group_name: str = "FB Group",
        is_valid_pc_hardware: bool = True
    ) -> bool:
        """Send subtle grey Discord Embed for Phase-1 passed posts that were skipped in Phase 2."""
        if not self.enabled or not self.webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in self.webhook_url:
            return False

        payload = self.format_skipped_embed_payload(
            hardware_name=hardware_name,
            asking_price=asking_price,
            estimated_market_price=estimated_market_price,
            deal_score=deal_score,
            verdict=verdict,
            reasoning=reasoning,
            post_url=post_url,
            group_name=group_name,
            is_valid_pc_hardware=is_valid_pc_hardware
        )

        try:
            logger.info(f"Sending Discord Skipped alert for [{hardware_name}]...")
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Discord skipped alert: {e}")
            return False

    def send_session_expired_alert(self, current_url: str = "") -> bool:
        """Send urgent Red Alert Discord Embed notification when Facebook cookies expire or session is invalidated."""
        if not self.enabled or not self.webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in self.webhook_url:
            return False

        embed = {
            "title": "🚨 [URGENT] FACEBOOK SESSION EXPIRED",
            "description": "**Sesi Login Facebook Kedaluwarsa!**\nBot FacebookSnoof ter-redirect ke halaman login Facebook. Pemindaian dihentikan sementara sampai cookie diperbarui.",
            "color": 0xE74C3C,  # Crimson Red
            "fields": [
                {
                    "name": "🔗 Target URL Redirect",
                    "value": current_url if current_url else "https://www.facebook.com/login/",
                    "inline": False
                },
                {
                    "name": "🛠️ Solusi Perbaikan",
                    "value": "1. Jalankan `python engine/auth.py` di PC lokal.\n2. Login ke Facebook & tekan Enter.\n3. Upload file `config/storage_state.json` baru ke server.",
                    "inline": False
                }
            ],
            "footer": {
                "text": "🚨 FacebookSnoof Security Monitor • Immediate User Action Required"
            }
        }

        payload = {
            "username": "🚨 FacebookSnoof System Alert",
            "embeds": [embed]
        }

        try:
            logger.info("Sending Discord Session Expired alert...")
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Discord session expired alert: {e}")
            return False

    def send_cookie_update_success_alert(self) -> bool:
        """Send Green Discord Embed confirmation when Facebook session cookies are successfully updated via /setcookie."""
        if not self.enabled or not self.webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in self.webhook_url:
            return False

        embed = {
            "title": "✅ FACEBOOK SESSION COOKIES UPDATED",
            "description": "**Sesi Cookie Facebook Berhasil Diperbarui dari HP!**\nFile `config/storage_state.json` baru telah dibuat dan berlaku selama 2 TAHUN KE DEPAN.\n\nSiklus pemindaian grup 15 menit otomatis dilanjutkan secara normal.",
            "color": 0x2ECC71,  # Emerald Green
            "footer": {
                "text": "FacebookSnoof Session Manager • Active Cookie Protection"
            }
        }

        payload = {
            "username": "🔑 FacebookSnoof Session Manager",
            "embeds": [embed]
        }

        try:
            logger.info("Sending Discord Cookie Update Success alert...")
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Discord cookie update success alert: {e}")
            return False


def start_discord_command_listener(bot_token: str, webhook_url: str = "") -> None:
    """Start a background Discord Bot listener for `/setcookie` or `!setcookie` commands in channel messages."""
    import re
    import threading
    if not bot_token or "YOUR_DISCORD_BOT_TOKEN" in bot_token:
        logger.info("Discord Bot Token not configured. Skipping background /setcookie command listener.")
        return

    try:
        import discord
        from discord.ext import commands
    except ImportError:
        logger.error("`discord.py` package is not installed. Unable to start Discord command listener.")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix=["/", "!"], intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"Discord Command Listener Bot logged in as [{bot.user}] (ID: {bot.user.id}). Ready for /setcookie commands!")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return

        content_lower = message.content.lower()
        if "setcookie" in content_lower or ("c_user=" in content_lower and "xs=" in content_lower):
            logger.info(f"Received Discord cookie update command from user [{message.author}]...")
            cookie_text = re.sub(r"^[/\!]setcookie\s*", "", message.content, flags=re.IGNORECASE)
            
            from engine.auth import update_storage_state_from_cookie_string
            success = update_storage_state_from_cookie_string(cookie_text)
            
            if success:
                embed = discord.Embed(
                    title="✅ FACEBOOK SESSION COOKIES UPDATED",
                    description="**Sesi Cookie Facebook Berhasil Diperbarui dari HP!**\nFile `config/storage_state.json` baru telah dibuat dan berlaku selama 2 TAHUN KE DEPAN.\n\nSiklus pemindaian grup 15 menit otomatis dilanjutkan secara normal.",
                    color=0x2ECC71
                )
                embed.set_footer(text="FacebookSnoof Session Manager • Active Cookie Protection")
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("❌ **GAGAL:** Format cookie tidak valid. Pastikan pesan mengandung `c_user=...` dan `xs=...`!")

        await bot.process_commands(message)

    def _run_bot():
        try:
            bot.run(bot_token)
        except Exception as e:
            logger.error(f"Discord Bot Command Listener encountered an error: {e}")

    thread = threading.Thread(target=_run_bot, daemon=True)
    thread.start()
    logger.info("Background Discord Command Listener thread launched.")
