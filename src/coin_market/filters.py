from . import Coins, OrderBooks
from .provider_name import ProviderName


def filter_coins_by_provider(coins: Coins, provider: ProviderName) -> Coins:
    filtered = Coins()
    for coin in coins.coins.values():
        if coin.provider == provider:
            filtered.upsert(coin)
    return filtered


def filter_orderbooks_by_provider(books: OrderBooks, provider: ProviderName) -> OrderBooks:
    filtered = OrderBooks()
    for book in books.books.values():
        if book.get_provider() == provider:
            filtered.upsert(book)
    return filtered