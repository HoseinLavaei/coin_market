import os
from zoneinfo import ZoneInfo

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
INTERVAL = int(os.getenv("INTERVAL", "60"))
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))
