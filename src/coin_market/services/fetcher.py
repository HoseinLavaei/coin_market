import asyncio

from ..domain import Quote, Base, Coins, OrderBooks
from ..infrastructure.providers import (
    AbanTetherProvider, BitpinProvider, ExirProvider, NobitexProvider,
    OkexProvider, OmpfinexProvider, RamzinexProvider, TabdealProvider, WallexProvider
)


async def fetch_all() -> tuple[Coins, OrderBooks]:
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

    # OTC
    tasks = [p.get_otc(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Coins):
            r = r.to_timezone()
            for coin in r.coins.values():
                coins_out.upsert(coin)

    # Order books
    tasks = [p.get_orderbook(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, OrderBooks):
            r = r.to_timezone()
            for book in r.books.values():
                books_out.upsert(book)

    return coins_out, books_out
