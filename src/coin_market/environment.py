"""
Loads and validates all required environment variables.
Provides constants used across the application, including bot tokens,
database URL, update interval, key expiry, and timezone.
"""

import os
from zoneinfo import ZoneInfo

# Telegram bot tokens
BROADCAST_BOT_TOKEN = os.getenv("BROADCAST_BOT_TOKEN")
CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN")
if not BROADCAST_BOT_TOKEN:
    raise ValueError("BROADCAST_BOT_TOKEN environment variable not set")
if not CONTROL_BOT_TOKEN:
    raise ValueError("CONTROL_BOT_TOKEN environment variable not set")

# Cache update interval in seconds
INTERVAL = int(os.getenv("INTERVAL", "60"))

# How long a pending subscription key remains valid (seconds)
KEY_EXPIRY_SECONDS = int(os.getenv("KEY_EXPIRY_SECONDS", "300"))

# PostgreSQL database URL (asyncpg format)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Timezone used for all timestamps and display
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))
# Telegram bot username (without @)
BROADCAST_BOT_USERNAME = os.getenv("BROADCAST_BOT_USERNAME", "coin_market_monitor_bot")