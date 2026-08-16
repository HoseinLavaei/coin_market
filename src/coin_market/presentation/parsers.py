"""
Command‑line argument parsing for the /prices command.
Supports both --key value and key=value styles.
"""

from decimal import Decimal
from typing import cast

from ..domain import ProviderName


def _handle_dash_arg(i: int, args: list[str]) -> tuple[str, str | None, int] | None:
    """Parse --key value pattern. Returns (key, value, consumed_count) or None."""
    token = args[i]
    if not (token.startswith("--") and len(token) > 2):
        return None
    key = token[2:].lower()
    if key == "stop":
        return "stop", "true", 1
    if i + 1 >= len(args):
        return "error", f"Missing value for option: {key}", 1
    return key, args[i + 1], 2


def _handle_equals_arg(token: str) -> tuple[str, str] | None:
    """Parse key=value pattern. Returns (key, value) or None."""
    if "=" not in token:
        return None
    key, value = token.split("=", 1)
    key = key.lower()
    if key == "stop":
        return "stop", "true"
    return key, value


def _handle_stop_arg(token: str) -> bool:
    """Return True if token is a plain 'stop'."""
    return token.lower() == "stop"


def _extract_arg_pairs(args: list[str]) -> tuple[dict[str, str], list[str]]:
    """Extract all named arguments from the command line. Returns (pairs, errors)."""
    pairs: dict[str, str] = {}
    errors: list[str] = []

    i = 0
    while i < len(args):
        token = args[i]

        dash_result = _handle_dash_arg(i, args)
        if dash_result is not None:
            key, value, consumed = dash_result
            if key == "error":
                errors.append(value or "Unknown error")
            else:
                pairs[key] = cast(str, value)
            i += consumed
            continue

        eq_result = _handle_equals_arg(token)
        if eq_result is not None:
            key, value = eq_result
            pairs[key] = value
            i += 1
            continue

        if _handle_stop_arg(token):
            pairs["stop"] = "true"
            i += 1
            continue

        errors.append(token)
        i += 1

    return pairs, errors


def _parse_provider(value: str) -> ProviderName:
    """Convert a string to a ProviderName enum."""
    try:
        return ProviderName[value.upper()]
    except KeyError:
        raise ValueError(f"Invalid provider: {value}")


def _parse_type_filter(value: str) -> str:
    """Normalize type filter to uppercase 'OTC' or 'P2P'."""
    lower = value.lower()
    if lower not in ("otc", "p2p"):
        raise ValueError(f"Invalid type: {value}")
    return lower.upper()


def _parse_volume(value: str) -> Decimal:
    """Convert string to Decimal."""
    try:
        return Decimal(value)
    except ValueError:
        raise ValueError(f"Invalid volume: {value}")


def _parse_repeat_interval(value: str) -> int:
    """Convert string to a positive integer."""
    try:
        interval = int(value)
        if interval <= 0:
            raise ValueError("Interval must be positive")
        return interval
    except ValueError:
        raise ValueError(f"Invalid repeat interval: {value}")


def parse_prices_args(args: list[str]) -> tuple[
    ProviderName | None, str | None, Decimal | None, int | None, bool, int | None]:
    """
    Main parser for /prices arguments.
    Returns: (provider, type_filter, volume, repeat_interval, stop_flag, chat_id)
    """
    pairs, errors = _extract_arg_pairs(args)
    if errors:
        raise ValueError(f"Invalid arguments: {', '.join(errors)}")

    provider_str = pairs.get("provider")
    type_str = pairs.get("type")
    volume_str = pairs.get("volume")
    repeat_str = pairs.get("repeat") or pairs.get("watch")
    stop_str = pairs.get("stop")
    chat_id_str = pairs.get("chat_id")

    provider = _parse_provider(provider_str) if provider_str is not None else None
    type_filter = _parse_type_filter(type_str) if type_str is not None else None
    volume = _parse_volume(volume_str) if volume_str is not None else None
    repeat_interval = _parse_repeat_interval(repeat_str) if repeat_str is not None else None
    stop_flag = stop_str == "true"

    chat_id = None
    if chat_id_str is not None:
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            raise ValueError(f"Invalid chat_id: {chat_id_str}")

    known_keys = {"provider", "type", "volume", "repeat", "watch", "stop", "chat_id"}
    unknown_keys = [k for k in pairs.keys() if k not in known_keys]
    if unknown_keys:
        raise ValueError(f"Unknown options: {', '.join(unknown_keys)}")

    return provider, type_filter, volume, repeat_interval, stop_flag, chat_id
