import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class WallexProvider:
    """Wallex exchange API provider."""
    provider_name = ProviderName.WALLEX

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        """Map Quote enum to Wallex currency code and multiplier."""
        if quote == Quote.RLS:
            return "TMN", 10
        elif quote == Quote.USD:
            return "USDT", 1
        return None

    @classmethod
    def _build_order_list(cls, entries: list, mult: int, q: Quote, b: Base, now: datetime.datetime,
                          key: str = "price") -> list[Order]:
        """Build Order list from price/quantity entries."""
        return [
            Order(
                coin=Coin(
                    provider=cls.provider_name,
                    base=b,
                    quote=q,
                    buy_price=Decimal(str(e[key])) * mult,
                    sell_price=Decimal(str(e[key])) * mult,
                    timestamp=now,
                ),
                quantity=Decimal(str(e["quantity"])),
            )
            for e in entries
        ]

    @classmethod
    async def _fetch_otc_prices(cls, sem: asyncio.Semaphore, sym: str, b: Base, q: Quote, mult: int):
        """Fetch OTC buy/sell prices for a symbol."""
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
                buy_price = Decimal(str(buy_res["result"]["price"]).rstrip("0").rstrip(",")) * mult
                sell_price = Decimal(str(sell_res["result"]["price"]).rstrip("0").rstrip(",")) * mult
            except (KeyError, ValueError, TypeError):
                return None

            price_coin = Coin(
                provider=cls.provider_name,
                base=b,
                buy_price=buy_price,
                sell_price=sell_price,
                quote=q,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            return (q, b), price_coin

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """Fetch OTC prices from Wallex."""
        try:
            markets_data = await get_json("https://api.wallex.ir/v1/otc/markets")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        symbols = markets_data.get("result", {})
        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if not mapping:
                continue

            quote_string, multiplier = mapping
            for base in bases:
                symbol_name = f"{base.value}{quote_string}"
                if symbol_name in symbols:
                    tasks.append(cls._fetch_otc_prices(semaphore, symbol_name, base, quote, multiplier))

        results = await asyncio.gather(*tasks)

        result = Coins()
        for result_item in results:
            if result_item is not None:
                _, price_coin = result_item
                result.upsert(price_coin)

        return result

    @classmethod
    async def _fetch_single_orderbook(cls, sem: asyncio.Semaphore, mkey: str, b: Base, q: Quote, mult: int):
        """Fetch a single orderbook."""
        async with sem:
            try:
                ob_data = await get_json("https://api.wallex.ir/v1/depth", params={"symbol": mkey})
            except (OSError, ValueError, TimeoutError):
                return None

            if not ob_data.get("success"):
                return None

            bids_raw = ob_data.get("result", {}).get("bid", [])
            asks_raw = ob_data.get("result", {}).get("ask", [])
            now = datetime.datetime.now(datetime.timezone.utc)

            bids_list = cls._build_order_list(bids_raw, mult, q, b, now)
            asks_list = cls._build_order_list(asks_raw, mult, q, b, now)

            return (q, b), OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    def _should_fetch_orderbook(cls, stats: dict) -> bool:
        """Check if orderbook should be fetched based on stats."""
        return stats.get("lastPrice") != "-"

    @classmethod
    def _build_orderbook_tasks(cls, sem: asyncio.Semaphore, symbols: dict, quotes: list[Quote],
                               bases: list[Base]) -> list:
        """Build list of orderbook fetch tasks."""
        tasks = []
        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if not mapping:
                continue

            quote_string, multiplier = mapping
            for base in bases:
                market_key = f"{base.value}{quote_string}"
                if market_key in symbols:
                    stats = symbols[market_key].get("stats", {})
                    if cls._should_fetch_orderbook(stats):
                        tasks.append(cls._fetch_single_orderbook(sem, market_key, base, quote, multiplier))

        return tasks

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """Fetch spot order books from Wallex."""
        try:
            markets_data = await get_json("https://api.wallex.ir/v1/markets")
        except (OSError, ValueError, TimeoutError):
            return OrderBooks()

        symbols = markets_data.get("result", {}).get("symbols", {})
        semaphore = asyncio.Semaphore(5)

        tasks = cls._build_orderbook_tasks(semaphore, symbols, quotes, bases)
        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for result_item in results:
            if result_item is not None:
                _, orderbook = result_item
                final_result.upsert(orderbook)

        return final_result
