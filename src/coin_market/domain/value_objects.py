from decimal import Decimal


def indent_text(text: str, spaces: int = 4) -> str:
    if not text:
        return text
    indent = " " * spaces
    return "\n".join(f"{indent}{line}" for line in text.splitlines())


def build_subscription_description(
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int | None,
) -> str:
    parts = []
    if provider:
        parts.append(f"🏛️ provider={provider}")
    if type_filter:
        if type_filter == "OTC":
            parts.append("💰 type=OTC")
        elif type_filter == "P2P":
            parts.append("🤝 type=P2P")
        else:
            parts.append(f"type={type_filter}")
    if volume is not None:
        parts.append(f"📦 volume={volume}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}s")
    return " + ".join(parts) if parts else "📊 all data"
