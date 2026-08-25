import time
from datetime import datetime


def now_seconds() -> int:
    """Return current time as seconds since Unix epoch."""
    return int(time.time())


def now_minutes() -> int:
    """Return current time as minutes since Unix epoch."""
    return int(time.time() // 60)


def minutes_to_datetime(minutes: int) -> datetime:
    """Convert minutes since epoch to datetime."""
    return datetime.fromtimestamp(minutes * 60)


def datetime_to_minutes(dt: datetime) -> int:
    """Convert datetime to minutes since epoch."""
    return int(dt.timestamp() // 60)
