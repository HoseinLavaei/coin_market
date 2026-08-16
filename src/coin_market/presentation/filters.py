"""
Helper functions to filter market data collections by provider.
Used in the message builder.
"""

from ..domain import Coins, OrderBooks, ProviderName


def filter_coins_by_provider(coins: Coins, provider: ProviderName) -> Coins:
    """Return only coins from the given provider."""
    filtered = Coins()
    for coin in coins.coins.values():
        if coin.provider == provider:
            filtered.upsert(coin)
    return filtered


def filter_orderbooks_by_provider(books: OrderBooks, provider: ProviderName) -> OrderBooks:
    """Return only order books from the given provider."""
    filtered = OrderBooks()
    for book in books.books.values():
        if book.get_provider() == provider:
            filtered.upsert(book)
    return filtered
