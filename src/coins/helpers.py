from decimal import Decimal


def build_subscription_description(
        volume: Decimal | None,
        repeat_interval: int | None,
) -> str:
    """
    Build a human‑readable description of a subscription's filters.
    Supports comma-separated values for provider and type_filter.
    """
    parts = []
    if volume is not None:
        parts.append(f"📦 volume={volume}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}m")

    return " + ".join(parts) if parts else "📊 all data"
