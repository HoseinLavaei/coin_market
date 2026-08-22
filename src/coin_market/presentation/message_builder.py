"""
Builds the formatted text message for market data output.
Leverages __str__ methods from domain objects for formatting.
"""

from decimal import Decimal
from typing import Optional, Sequence, List

from ..domain import Coins, OrderBook, OrderBooks, Coin, Quote, Base, ProviderName


# ─── Provider parsing ───────────────────────────────────────

def _normalize_provider(provider: ProviderName | str | None) -> List[ProviderName]:
    """Convert provider input to a list of ProviderName enums."""
    if provider is None:
        return []
    if isinstance(provider, ProviderName):
        return [provider]
    if isinstance(provider, str):
        if "," in provider:
            result = []
            for name in provider.split(","):
                try:
                    result.append(ProviderName[name.strip().upper()])
                except KeyError:
                    pass
            return result
        try:
            return [ProviderName[provider.upper()]]
        except KeyError:
            return []
    return []


def _filter_keys(
        all_keys: list[tuple[ProviderName, Quote, Base]],
        provider_list: Sequence[ProviderName],
) -> list[tuple[ProviderName, Quote, Base]]:
    """Filter keys to selected providers, sorted by name."""
    if not provider_list:
        return sorted(all_keys, key=lambda x: x[0].value)
    provider_set = set(provider_list)
    return sorted(
        [k for k in all_keys if k[0] in provider_set],
        key=lambda x: x[0].value,
    )


# ─── Candidate collection ───────────────────────────────────

def _candidates_from_key(
        provider: ProviderName,
        quote: Quote,
        base: Base,
        coins: Coins,
        books: OrderBooks,
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> list[tuple[Coin, ProviderName, str]]:
    """Collect candidates (Coin, provider, type) from a single (provider, quote, base) key."""
    candidates = []
    if show_otc:
        coin = coins.coins.get((provider, quote, base))
        if coin is not None:
            candidates.append((coin, provider, "OTC"))
    if show_p2p:
        book = books.books.get((provider, quote, base))
        if book is not None:
            try:
                vwap_coin = book.get_by_volume(volume)
                candidates.append((vwap_coin, provider, "P2P"))
            except ValueError:
                pass
    return candidates


def _collect_candidates(
        coins: Coins,
        books: OrderBooks,
        keys: list[tuple[ProviderName, Quote, Base]],
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> list[tuple[Coin, ProviderName, str]]:
    """Collect all available (Coin, provider, type) candidates."""
    candidates = []
    for provider, quote, base in keys:
        candidates.extend(
            _candidates_from_key(provider, quote, base, coins, books, show_otc, show_p2p, volume)
        )
    return candidates


# ─── Best prices summary ────────────────────────────────────

def _get_best_prices(
        coins: Coins,
        books: OrderBooks,
        keys: list[tuple[ProviderName, Quote, Base]],
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> tuple[Optional[tuple[Coin, ProviderName, str]], Optional[tuple[Coin, ProviderName, str]]]:
    """Find the Best Buy and sell prices across all providers/types."""
    candidates = _collect_candidates(coins, books, keys, show_otc, show_p2p, volume)
    if not candidates:
        return None, None

    best_buy = min(candidates, key=lambda x: x[0].buy_price)
    best_sell = max(candidates, key=lambda x: x[0].sell_price)
    return best_buy, best_sell


def _format_best_summary(
        best_buy: Optional[tuple[Coin, ProviderName, str]],
        best_sell: Optional[tuple[Coin, ProviderName, str]],
) -> str:
    """Format Best Buy/sell as a small summary block."""
    if best_buy is None and best_sell is None:
        return "📭 No market data available."

    lines = ["🏆 Best"]
    if best_buy is not None:
        coin, provider, typ = best_buy
        buy_str, _ = coin.get_formatted_price()
        lines.append(f"    🟢 {buy_str} ({provider.value}, {typ})")
    if best_sell is not None:
        coin, provider, typ = best_sell
        _, sell_str = coin.get_formatted_price()
        lines.append(f"    🔴 {sell_str} ({provider.value}, {typ})")

    return "\n".join(lines)


# ─── Determine which types to show ─────────────────────────

def _determine_show_types(type_filter: str | None) -> tuple[bool, bool]:
    """Return (show_otc, show_p2p) based on type_filter."""
    if type_filter and type_filter.upper() == "OTC":
        return True, False
    if type_filter and type_filter.upper() == "P2P":
        return False, True
    return True, True  # default: show both


# ─── Formatting lines for provider block ────────────────────

def _format_otc_line(coin: Coin | None) -> str:
    """Return the formatted OTC line for a provider."""
    return f"  💰 OTC:  {str(coin) if coin else '(No data)'}"


def _format_p2p_line(book: OrderBook | None, volume: Decimal) -> str:
    """Return the formatted P2P line for a provider."""
    if book is None:
        return "  📚 P2P: (No data)"
    try:
        vwap = book.get_by_volume(volume)
        return f"  📚 P2P:  {str(vwap)}"
    except ValueError:
        return "  📚 P2P: (No data)"


def _build_provider_block(
        provider: ProviderName,
        quote: Quote,
        base: Base,
        coins: Coins,
        books: OrderBooks,
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> str:
    """Build a single provider block."""
    lines = [f"📦 {provider.value}"]

    if show_otc:
        coin = coins.coins.get((provider, quote, base))
        lines.append(_format_otc_line(coin))

    if show_p2p:
        book = books.books.get((provider, quote, base))
        lines.append(_format_p2p_line(book, volume))

    return "\n".join(lines)


def _build_provider_blocks(
        keys: list[tuple[ProviderName, Quote, Base]],
        coins: Coins,
        books: OrderBooks,
        show_otc: bool,
        show_p2p: bool,
        volume: Decimal,
) -> list[str]:
    """Build the formatted blocks for each provider."""
    return [
        _build_provider_block(provider, quote, base, coins, books, show_otc, show_p2p, volume)
        for provider, quote, base in keys
    ]


# ─── Main output builder ────────────────────────────────────

def build_prices_output(
        coins: Coins,
        books: OrderBooks,
        provider: ProviderName | str | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
) -> str:
    show_otc, show_p2p = _determine_show_types(type_filter)

    all_keys = list(set(coins.coins.keys()) | set(books.books.keys()))
    keys = _filter_keys(all_keys, _normalize_provider(provider))

    if not keys:
        return f"📭 No data available." + (f" for {provider}" if provider else "")

    vol = volume if volume is not None else Decimal(1)

    blocks = _build_provider_blocks(keys, coins, books, show_otc, show_p2p, vol)

    summary = _format_best_summary(
        *_get_best_prices(coins, books, keys, show_otc, show_p2p, vol)
    )

    return f"{summary}\n\n" + "\n\n".join(blocks)
