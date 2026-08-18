"""
Builds the formatted text message for market data output.
Groups OTC and P2P data by provider and applies filters.
"""

from decimal import Decimal
from typing import Sequence, List

from ..domain import Coins, OrderBooks, Coin, OrderBook, Quote, Base, ProviderName


# ─── Helper: Parse provider string ─────────────────────────

def _parse_provider_string(provider_str: str) -> List[ProviderName]:
    """
    Parse a provider string (single or comma-separated) into a list of ProviderName enums.
    Invalid names are silently ignored.
    """
    if "," in provider_str:
        names = [name.strip() for name in provider_str.split(",") if name.strip()]
        result = []
        for name in names:
            try:
                result.append(ProviderName[name.upper()])
            except KeyError:
                pass
        return result
    else:
        try:
            return [ProviderName[provider_str.upper()]]
        except KeyError:
            return []


# ─── Helper: Normalize provider input ──────────────────────

def _normalize_provider(provider: ProviderName | str | None) -> List[ProviderName]:
    """
    Convert provider input to a list of ProviderName enums.
    - None → empty list (means "all providers")
    - ProviderName → single-item list
    - String → parsed via _parse_provider_string()
    """
    if provider is None:
        return []

    if isinstance(provider, ProviderName):
        return [provider]

    if isinstance(provider, str):
        return _parse_provider_string(provider)

    return []


def _filter_keys(
        all_keys: list[tuple[ProviderName, Quote, Base]],
        provider_list: Sequence[ProviderName],
) -> list[tuple[ProviderName, Quote, Base]]:
    """Filter keys to only those matching the given provider list."""
    if not provider_list:
        return sorted(all_keys, key=lambda x: x[0].value)

    provider_set = set(provider_list)
    return sorted(
        [k for k in all_keys if k[0] in provider_set],
        key=lambda x: x[0].value,
    )


def _get_display_keys(
        coins: Coins,
        books: OrderBooks,
        provider: ProviderName | str | None,
) -> list[tuple[ProviderName, Quote, Base]]:
    """
    Determine the list of (provider, quote, base) keys to display.
    """
    all_keys = list(set(coins.coins.keys()) | set(books.books.keys()))
    provider_list = _normalize_provider(provider)
    return _filter_keys(all_keys, provider_list)


# ─── Formatting helpers ─────────────────────────────────────

def _format_otc_section(coin: Coin | None) -> str:
    if coin is None:
        return "  💰 OTC: (No data)"
    lines = str(coin).splitlines()
    return "  💰 OTC:\n" + "\n".join(f"  {line}" for line in lines)


def _format_p2p_section(book: OrderBook | None, volume: Decimal) -> str:
    if book is None:
        return "  📚 P2P: (No data)"
    try:
        vwap_coin = book.get_by_volume(volume)
        lines = str(vwap_coin).splitlines()
        return "  📚 P2P:\n" + "\n".join(f"  {line}" for line in lines)
    except ValueError:
        return "  📚 P2P: (No data)"


def _format_provider_block(
        provider_key: ProviderName,
        quote: Quote,
        base: Base,
        coins: Coins,
        books: OrderBooks,
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> str:
    lines = [f"📦 {provider_key.value} / {base.value} / {quote.value}"]
    if show_otc:
        coin = coins.coins.get((provider_key, quote, base))
        lines.append(_format_otc_section(coin))
    if show_p2p:
        book = books.books.get((provider_key, quote, base))
        lines.append(_format_p2p_section(book, volume))
    return "\n".join(lines)


# ─── Main output builder ────────────────────────────────────

def build_prices_output(
        coins: Coins,
        books: OrderBooks,
        provider: ProviderName | str | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
) -> str:
    # ─── Determine which types to show ──────────────────────
    if type_filter:
        if "," in type_filter:
            show_otc = True
            show_p2p = True
        elif type_filter.upper() == "OTC":
            show_otc = True
            show_p2p = False
        elif type_filter.upper() == "P2P":
            show_otc = False
            show_p2p = True
        else:
            show_otc = True
            show_p2p = True
    else:
        show_otc = True
        show_p2p = True

    keys = _get_display_keys(coins, books, provider)
    if not keys:
        if provider:
            return f"📭 No data available for provider {provider}."
        return "📭 No data available."

    vol = volume if volume is not None else Decimal(1)
    blocks = [
        _format_provider_block(p, q, b, coins, books, show_otc, show_p2p, vol)
        for p, q, b in keys
    ]
    return "\n".join(blocks)
