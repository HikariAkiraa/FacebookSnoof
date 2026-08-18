"""Notifier package initialization for FacebookSnoof."""
from .telegram import TelegramNotifier
from .discord import DiscordNotifier

__all__ = ["TelegramNotifier", "DiscordNotifier"]
