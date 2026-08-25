from decimal import Decimal


def build_subscription_description(
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int | None,
) -> str:
    """
    Build a human‑readable description of a subscription's filters.
    Supports comma-separated values for provider and type_filter.
    """
    parts = []

    if provider:
        if "," in provider:
            provider_names = provider.split(",")
            parts.append(f"🏛️ providers={', '.join(provider_names)}")
        else:
            parts.append(f"🏛️ provider={provider}")

    if type_filter:
        if "," in type_filter:
            type_names = type_filter.split(",")
            parts.append(f"📊 types={', '.join(type_names)}")
        else:
            parts.append(f"📊 type={type_filter}")

    if volume is not None:
        parts.append(f"📦 volume={volume}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}s")

    return " + ".join(parts) if parts else "📊 all data"
