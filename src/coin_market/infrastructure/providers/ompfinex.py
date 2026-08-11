import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ...domain import Coin, Quote, Base, Coins, OrderBooks, ProviderName, Order, OrderBook


class OmpfinexProvider:
    provider_name = ProviderName.OMPFINEX

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    def _build_orders(cls, prices_data: list, quote: Quote, base: Base, now: datetime.datetime) -> list[Order]:
        return [
            Order(
                coin=Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=Decimal(str(price)) / 10,
                    raw_sell_price=Decimal(str(price)) / 10,
                    buy_fee=Decimal(0.35),
                    sell_fee=Decimal(0.35),
                    timestamp=now,
                ),
                quantity=Decimal(str(amount)),
            )
            for price, amount in prices_data
        ]

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> str | None:
        if quote == Quote.TMN:
            return "IRR"
        elif quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    async def _fetch_market_map(cls) -> dict[tuple[str, str], int]:
        """Fetch market map: (quote_currency_id, base_currency_id) -> market_id."""
        try:
            markets_json = await get_json("https://api.ompfinex.com/v1/market")
        except (OSError, ValueError, TimeoutError):
            return {}
        if markets_json.get("status") != "OK":
            return {}
        market_map: dict[tuple[str, str], int] = {}
        for market in markets_json.get("data", []):
            quote_id = market["quote_currency"]["id"]
            base_id = market["base_currency"]["id"]
            market_map[(quote_id, base_id)] = market["id"]
        return market_map

    @classmethod
    async def _fetch_single_orderbook(cls, semaphore: asyncio.Semaphore, mid: int, b: Base, q: Quote):
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
            bids_list = cls._build_orders(bids_raw, q, b, now)
            asks_list = cls._build_orders(asks_raw, q, b, now)
            return (q, b), OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        market_map = await cls._fetch_market_map()
        if not market_map:
            return OrderBooks()
        semaphore = asyncio.Semaphore(5)
        tasks = []
        for quote in quotes:
            quote_id = cls._get_quote_mapping(quote)
            if not quote_id:
                continue
            for base in bases:
                market_id = market_map.get((quote_id, base.value))
                if market_id is not None:
                    tasks.append(cls._fetch_single_orderbook(semaphore, market_id, base, quote))
        results = await asyncio.gather(*tasks)
        final_result = OrderBooks()
        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)
        return final_result
