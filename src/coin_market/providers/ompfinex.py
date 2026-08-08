import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class OmpfinexProvider:
    provider_name = ProviderName.OMPFINEX

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    def _build_orders(cls, prices_data: list, multiplier: int, quote: Quote, base: Base, now: datetime.datetime) -> \
    list[Order]:
        """Build Order objects from price/amount pairs."""
        return [
            Order(
                coin=Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    _buy_price=Decimal(str(price)) * multiplier,
                    _sell_price=Decimal(str(price)) * multiplier,
                    buy_fee=Decimal(0.35),
                    sell_fee=Decimal(0.35),
                    timestamp=now,
                ),
                quantity=Decimal(str(amount)),
            )
            for price, amount in prices_data
        ]

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        """Map Quote enum to Ompfinex currency ID and multiplier."""
        if quote == Quote.RLS:
            return "IRR", 1
        elif quote == Quote.USD:
            return "USDT", 1
        return None

    @classmethod
    async def _fetch_market_map(cls) -> dict:
        """Fetch and build market map from Ompfinex API."""
        try:
            markets_json = await get_json("https://api.ompfinex.com/v1/market")
        except (OSError, ValueError, TimeoutError):
            return {}

        if markets_json.get("status") != "OK":
            return {}

        market_map = {}
        for market in markets_json.get("data", []):
            quote_id = market["quote_currency"]["id"]
            base_id = market["base_currency"]["id"]
            market_map[(quote_id, base_id)] = market["id"]

        return market_map

    @classmethod
    async def _fetch_single_orderbook(cls, semaphore: asyncio.Semaphore, mid: int, b: Base, q: Quote, mult: int):
        """Fetch a single orderbook."""
        async with semaphore:
            try:
                data = await get_json(f"https://api.ompfinex.com/v1/market/{mid}/depth", {"limit": "200"})
            except (OSError, ValueError, TimeoutError):
                return None

            if data.get("status") != "OK":
                return None

            result_data = data.get("data", {})
            bids_raw = result_data.get("bids", [])
            asks_raw = result_data.get("asks", [])
            now = datetime.datetime.now(datetime.timezone.utc)

            bids_list = cls._build_orders(bids_raw, mult, q, b, now)
            asks_list = cls._build_orders(asks_raw, mult, q, b, now)

            return (q, b), OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch spot order books from Ompfinex.
        Uses /v1/market endpoint to get market IDs, then /v1/market/{id}/depth for order books.
        """
        market_map = await cls._fetch_market_map()
        if not market_map:
            return OrderBooks()

        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            quote_mapping = cls._get_quote_mapping(quote)
            if not quote_mapping:
                continue

            quote_id, multiplier = quote_mapping
            for base in bases:
                base_id = base.value
                market_id: int | None = market_map.get((quote_id, base_id))
                if market_id is not None:
                    tasks.append(cls._fetch_single_orderbook(semaphore, market_id, base, quote, multiplier))

        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for result_item in results:
            if result_item is not None:
                _, orderbook = result_item
                final_result.upsert(orderbook)

        return final_result
