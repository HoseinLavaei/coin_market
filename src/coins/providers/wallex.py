import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class WallexProvider:
    """Fetches OTC and order book data from Wallex exchange."""
    provider_name: ProviderName = ProviderName.WALLEX

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> Optional[str]:
        if quote == Quote.TMN:
            return "TMN"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    def _build_order_list(
            cls,
            entries: list[dict[str, Any]],
            quote: Quote,
            base: Base,
            now: datetime.datetime,
            key: str = "price",
    ) -> list[Order]:
        orders: list[Order] = []
        for entry in entries:
            try:
                price = Decimal(str(entry[key]))
                quantity = Decimal(str(entry["quantity"]))
            except (KeyError, ValueError, TypeError):
                continue
            coin = Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
                raw_buy_price=price,
                raw_sell_price=price,
                buy_fee=Decimal(0.3),
                sell_fee=Decimal(0.3),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=quantity))
        return orders

    @classmethod
    async def _fetch_otc_prices(
            cls,
            sem: asyncio.Semaphore,
            symbol: str,
            base: Base,
            quote: Quote,
    ) -> Optional[tuple[tuple[Quote, Base], Coin]]:
        async with sem:
            try:
                buy_task = get_json("https://api.wallex.ir/v1/otc/price", params={"symbol": symbol, "side": "BUY"})
                sell_task = get_json("https://api.wallex.ir/v1/otc/price", params={"symbol": symbol, "side": "SELL"})
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
                base=base,
                quote=quote,
                raw_buy_price=buy_price,
                raw_sell_price=sell_price,
                buy_fee=Decimal(0),
                sell_fee=Decimal(0),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            return (quote, base), coin

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        try:
            markets_data = await get_json("https://api.wallex.ir/v1/otc/markets")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        symbols: dict[str, Any] = markets_data.get("result", {})
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

        for item in results:
            if item is not None:
                _, coin = item
                result.upsert(coin)

        return result

    @classmethod
    async def _fetch_single_orderbook(
            cls,
            sem: asyncio.Semaphore,
            market_key: str,
            base: Base,
            quote: Quote,
    ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
        async with sem:
            try:
                data = await get_json("https://api.wallex.ir/v1/depth", params={"symbol": market_key})
            except (OSError, ValueError, TimeoutError):
                return None

            if not data.get("success"):
                return None

            result_data = data.get("result", {})
            bids_raw: list[dict[str, Any]] = result_data.get("bid", [])
            asks_raw: list[dict[str, Any]] = result_data.get("ask", [])
            if not bids_raw and not asks_raw:
                return None

            now = datetime.datetime.now(datetime.timezone.utc)
            bids = cls._build_order_list(bids_raw, quote, base, now)
            asks = cls._build_order_list(asks_raw, quote, base, now)
            if not bids and not asks:
                return None

            return (quote, base), OrderBook(asks=asks, bids=bids)

    @classmethod
    def _should_fetch_orderbook(cls, stats: dict[str, Any]) -> bool:
        """Return True if the market has a valid last price."""
        return stats.get("lastPrice") != "-"

    @classmethod
    def _build_orderbook_tasks(
            cls,
            sem: asyncio.Semaphore,
            symbols: dict[str, Any],
            quotes: list[Quote],
            bases: list[Base],
    ):
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

        symbols: dict[str, Any] = markets_data.get("result", {}).get("symbols", {})
        semaphore = asyncio.Semaphore(5)

        tasks = cls._build_orderbook_tasks(semaphore, symbols, quotes, bases)
        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for item in results:
            if item is not None:
                _, orderbook = item
                final_result.upsert(orderbook)

        return final_result
