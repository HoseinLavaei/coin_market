from decimal import Decimal
from typing import Optional


def build_subscription_description(
        volume: Optional[Decimal],
        repeat_interval: Optional[int],
) -> str:
    """
    Build a human‑readable description of a subscription's filters.
    Supports comma-separated values for provider and type_filter.
    """
    parts = []
    if volume is not None:
        # Format volume without scientific notation
        parts.append(f"📦 volume={format(volume, 'f')}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}m")

    return " + ".join(parts) if parts else "📊 all data"
