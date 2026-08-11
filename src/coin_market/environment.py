import os
from zoneinfo import ZoneInfo

BROADCAST_BOT_TOKEN = os.getenv("BROADCAST_BOT_TOKEN")
CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN")
if not BROADCAST_BOT_TOKEN:
    raise ValueError("BROADCAST_BOT_TOKEN environment variable not set")
if not CONTROL_BOT_TOKEN:
    raise ValueError("CONTROL_BOT_TOKEN environment variable not set")
INTERVAL = int(os.getenv("INTERVAL", "60"))
KEY_EXPIRY_SECONDS = int(os.getenv("KEY_EXPIRY_SECONDS", "300"))
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))
