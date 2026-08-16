"""
Builds the formatted text message for market data output.
Groups OTC and P2P data by provider and applies filters.
"""

from decimal import Decimal

from ..domain import Coins, OrderBooks, Coin, OrderBook, Quote, Base, ProviderName


def _get_display_keys(coins: Coins, books: OrderBooks, provider: ProviderName | None) -> list[
    tuple[ProviderName, Quote, Base]]:
    """
    Determine the list of (provider, quote, base) keys to display.
    If a provider is specified, only show that provider.
    """
    all_keys = set(coins.coins.keys()) | set(books.books.keys())
    if provider:
        return [k for k in all_keys if k[0] == provider]
    return sorted(all_keys, key=lambda x: x[0].value)


def _format_otc_section(coin: Coin | None) -> str:
    """Format a single OTC price entry."""
    if coin is None:
        return "  💰 OTC: (No data)"
    lines = str(coin).splitlines()
    return "  💰 OTC:\n" + "\n".join(f"  {line}" for line in lines)


def _format_p2p_section(book: OrderBook | None, volume: Decimal) -> str:
    """Format a single P2P order book entry (shows VWAP for the given volume)."""
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
    """Format a complete block for a single provider."""
    lines = [f"📦 {provider_key.value} / {base.value} / {quote.value}"]
    if show_otc:
        coin = coins.coins.get((provider_key, quote, base))
        lines.append(_format_otc_section(coin))
    if show_p2p:
        book = books.books.get((provider_key, quote, base))
        lines.append(_format_p2p_section(book, volume))
    return "\n".join(lines)


def build_prices_output(
        coins: Coins,
        books: OrderBooks,
        provider: ProviderName | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
) -> str:
    """
    Build the full market data output string.
    Shows OTC and/or P2P sections based on type_filter, and filters by provider if given.
    """
    show_otc = type_filter is None or type_filter == "OTC"
    show_p2p = type_filter is None or type_filter == "P2P"
    keys = _get_display_keys(coins, books, provider)
    if not keys:
        if provider:
            return f"📭 No data available for provider {provider.value}."
        return "📭 No data available."
    vol = volume if volume is not None else Decimal(1)
    blocks = [
        _format_provider_block(p, q, b, coins, books, show_otc, show_p2p, vol)
        for p, q, b in keys
    ]
    return "\n".join(blocks)
