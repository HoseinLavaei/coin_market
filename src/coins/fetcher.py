"""
Aggregates data from all exchange providers.
Fetches OTC prices and order books concurrently and returns unified collections.
"""

import asyncio

from .enums import Quote, Base
from .models import Coins, OrderBooks
from .providers import (
    AbanTetherProvider,
    BitpinProvider,
    ExirProvider,
    NobitexProvider,
    OkexProvider,
    OmpfinexProvider,
    RamzinexProvider,
    TabdealProvider,
    WallexProvider,
)


async def fetch_all() -> tuple[Coins, OrderBooks]:
    """
    Fetch OTC and order book data from all supported providers.
    Returns a tuple of (Coins, OrderBooks) with timezone‑adjusted timestamps.
    """
    providers = [
        AbanTetherProvider(),
        BitpinProvider(),
        ExirProvider(),
        NobitexProvider(),
        OkexProvider(),
        OmpfinexProvider(),
        RamzinexProvider(),
        TabdealProvider(),
        WallexProvider(),
    ]
    quotes = [Quote.TMN]
    bases = [Base.USDT]

    coins_out = Coins()
    books_out = OrderBooks()

    # Fetch OTC prices
    tasks = [p.get_otc(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Coins):
            r = r.to_timezone()
            for coin in r.coins.values():
                coins_out.upsert(coin)

    # Fetch order books
    tasks = [p.get_orderbook(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, OrderBooks):
            r = r.to_timezone()
            for book in r.books.values():
                books_out.upsert(book)

    return coins_out, books_out
