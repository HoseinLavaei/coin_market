"""
Loads and validates all required environment variables.
"""

import os
from zoneinfo import ZoneInfo

# ─── Telegram Bot Tokens ────────────────────────────────────
BROADCAST_BOT_TOKEN = os.getenv("BROADCAST_BOT_TOKEN")
CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN")
if not BROADCAST_BOT_TOKEN:
    raise ValueError("BROADCAST_BOT_TOKEN environment variable not set")
if not CONTROL_BOT_TOKEN:
    raise ValueError("CONTROL_BOT_TOKEN environment variable not set")

# ─── Database ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# ─── Celery / Redis ─────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ─── Other settings ─────────────────────────────────────────
INTERVAL = int(os.getenv("INTERVAL", "60"))
KEY_EXPIRY_SECONDS = int(os.getenv("KEY_EXPIRY_SECONDS", "300"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))
BROADCAST_BOT_USERNAME = os.getenv("BROADCAST_BOT_USERNAME", "coin_market_monitor_bot")
