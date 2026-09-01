import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class OmpfinexProvider:
    """Fetches order book data from Ompfinex exchange. OTC is not supported."""
    provider_name: ProviderName = ProviderName.OMPFINEX

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    def _build_orders(
            cls,
            prices_data: list[list[Any]],
            quote: Quote,
            base: Base,
            now: datetime.datetime,
    ) -> list[Order]:
        orders: list[Order] = []
        for price, amount in prices_data:
            try:
                price_dec = Decimal(str(price)) / 10
                amount_dec = Decimal(str(amount))
            except (ValueError, TypeError):
                continue
            coin = Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
                raw_buy_price=price_dec,
                raw_sell_price=price_dec,
                buy_fee=Decimal(0.35),
                sell_fee=Decimal(0.35),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount_dec))
        return orders

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> Optional[str]:
        if quote == Quote.TMN:
            return "IRR"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    async def _fetch_market_map(cls) -> dict[tuple[str, str], int]:
        """Build a mapping of (quote_currency_id, base_currency_id) -> market_id."""
        try:
            data = await get_json("https://api.ompfinex.com/v1/market")
        except (OSError, ValueError, TimeoutError):
            return {}

        if data.get("status") != "OK":
            return {}

        market_map: dict[tuple[str, str], int] = {}
        for market in data.get("data", []):
            quote_id = market["quote_currency"]["id"]
            base_id = market["base_currency"]["id"]
            market_map[(quote_id, base_id)] = market["id"]

        return market_map

    @classmethod
    async def _fetch_single_orderbook(
            cls,
            semaphore: asyncio.Semaphore,
            market_id: int,
            base: Base,
            quote: Quote,
    ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
        async with semaphore:
            try:
                data = await get_json(
                    f"https://api.ompfinex.com/v1/market/{market_id}/depth",
                    {"limit": "1000000"},
                )
            except (OSError, ValueError, TimeoutError):
                return None

            if data.get("status") != "OK":
                return None

            result_data = data.get("data", {})
            bids_raw: list[list[Any]] = result_data.get("bids", [])
            asks_raw: list[list[Any]] = result_data.get("asks", [])
            if not bids_raw and not asks_raw:
                return None

            now = datetime.datetime.now(datetime.timezone.utc)
            bids = cls._build_orders(bids_raw, quote, base, now)
            asks = cls._build_orders(asks_raw, quote, base, now)
            if not bids and not asks:
                return None

            return (quote, base), OrderBook(asks=asks, bids=bids)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        market_map = await cls._fetch_market_map()
        if not market_map:
            return OrderBooks()

        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            quote_id = cls._get_quote_mapping(quote)
            if quote_id is None:
                continue

            for base in bases:
                market_id = market_map.get((quote_id, base.value))
                if market_id is not None:
                    tasks.append(cls._fetch_single_orderbook(semaphore, market_id, base, quote))

        results = await asyncio.gather(*tasks)
        final_result = OrderBooks()

        for result in results:
            if result is not None:
                _, orderbook = result
                final_result.upsert(orderbook)

        return final_result
