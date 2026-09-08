"""
Aggregates data from all exchange providers.
Fetches OTC prices and order books concurrently and returns unified collections.
"""

import asyncio

from src import logger
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

    otc_tasks = [p.get_otc(quotes, bases) for p in providers]
    p2p_tasks = [p.get_orderbook(quotes, bases) for p in providers]

    results = await asyncio.gather(*otc_tasks, *p2p_tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Task failed: {result}")
            continue
        elif isinstance(result, Coins):
            result = result.to_timezone()
            for coin in result.coins.values():
                coins_out.upsert(coin)
        elif isinstance(result, OrderBooks):
            result = result.to_timezone()
            for book in result.books.values():
                books_out.upsert(book)
        else:
            logger.error(f"Unexpected result type: {type(result)}")

    return coins_out, books_out