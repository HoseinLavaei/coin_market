import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class WallexProvider:
    """Fetches OTC and order book data from Wallex exchange."""
    provider_name = ProviderName.WALLEX

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> str | None:
        if quote == Quote.TMN:
            return "TMN"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    def _build_order_list(cls, entries: list, q: Quote, b: Base, now: datetime.datetime, key: str = "price") -> list[
        Order]:
        return [
            Order(
                coin=Coin(
                    provider=cls.provider_name,
                    base=b,
                    quote=q,
                    raw_buy_price=Decimal(str(e[key])),
                    raw_sell_price=Decimal(str(e[key])),
                    buy_fee=Decimal(0.3),
                    sell_fee=Decimal(0.3),
                    timestamp=now,
                ),
                quantity=Decimal(str(e["quantity"])),
            )
            for e in entries
        ]

    @classmethod
    async def _fetch_otc_prices(cls, sem: asyncio.Semaphore, sym: str, b: Base, q: Quote):
        async with sem:
            try:
                buy_task = get_json("https://api.wallex.ir/v1/otc/price", params={"symbol": sym, "side": "BUY"})
                sell_task = get_json("https://api.wallex.ir/v1/otc/price", params={"symbol": sym, "side": "SELL"})
                buy_res, sell_res = await asyncio.gather(buy_task, sell_task)
            except (OSError, ValueError, TimeoutError):
                return None

            if not buy_res.get("success") or not sell_res.get("success"):
                return None

            try:
                buy_price = Decimal(str(buy_res["result"]["price"]).rstrip("0").rstrip(","))
                sell_price = Decimal(str(sell_res["result"]["price"]).rstrip("0").rstrip(","))
            except (KeyError, ValueError, TypeError):
                return None

            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                raw_buy_price=buy_price,
                raw_sell_price=sell_price,
                buy_fee=Decimal(0),
                sell_fee=Decimal(0),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            return (q, b), coin

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        try:
            markets_data = await get_json("https://api.wallex.ir/v1/otc/markets")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        symbols = markets_data.get("result", {})
        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            quote_string = cls._get_quote_mapping(quote)
            if quote_string is None:
                continue

            for base in bases:
                symbol_name = f"{base.value}{quote_string}"
                if symbol_name in symbols:
                    tasks.append(cls._fetch_otc_prices(semaphore, symbol_name, base, quote))

        results = await asyncio.gather(*tasks)
        result = Coins()

        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

    @classmethod
    async def _fetch_single_orderbook(cls, sem: asyncio.Semaphore, mkey: str, b: Base, q: Quote):
        async with sem:
            try:
                data = await get_json("https://api.wallex.ir/v1/depth", params={"symbol": mkey})
            except (OSError, ValueError, TimeoutError):
                return None

            if not data.get("success"):
                return None

            result_data = data.get("result", {})
            bids_raw = result_data.get("bid", [])
            asks_raw = result_data.get("ask", [])
            now = datetime.datetime.now(datetime.timezone.utc)

            return (q, b), OrderBook(
                asks=cls._build_order_list(asks_raw, q, b, now),
                bids=cls._build_order_list(bids_raw, q, b, now),
            )

    @classmethod
    def _should_fetch_orderbook(cls, stats: dict) -> bool:
        """Return True if the market has a valid last price."""
        return stats.get("lastPrice") != "-"

    @classmethod
    def _build_orderbook_tasks(cls, sem: asyncio.Semaphore, symbols: dict, quotes: list[Quote],
                               bases: list[Base]) -> list:
        tasks = []

        for quote in quotes:
            quote_string = cls._get_quote_mapping(quote)
            if quote_string is None:
                continue

            for base in bases:
                market_key = f"{base.value}{quote_string}"
                if market_key in symbols:
                    stats = symbols[market_key].get("stats", {})
                    if cls._should_fetch_orderbook(stats):
                        tasks.append(cls._fetch_single_orderbook(sem, market_key, base, quote))

        return tasks

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        try:
            markets_data = await get_json("https://api.wallex.ir/v1/markets")
        except (OSError, ValueError, TimeoutError):
            return OrderBooks()

        symbols = markets_data.get("result", {}).get("symbols", {})
        semaphore = asyncio.Semaphore(5)

        tasks = cls._build_orderbook_tasks(semaphore, symbols, quotes, bases)
        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)

        return final_result
