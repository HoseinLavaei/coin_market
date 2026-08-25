import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, OrderBook, Order


class RamzinexProvider:
    """Fetches OTC and order book data from Ramzinex exchange."""
    provider_name = ProviderName.RAMZINEX

    @staticmethod
    def _clean_number(raw_value):
        if isinstance(raw_value, (int, float)):
            return Decimal(raw_value)
        if isinstance(raw_value, str):
            return Decimal(raw_value.replace(",", "").strip())
        raise ValueError(f"Unsupported type: {type(raw_value)}")

    @classmethod
    def _get_quote_string(cls, quote: Quote) -> str | None:
        if quote == Quote.TMN:
            return "irr"
        if quote == Quote.USD:
            return "usdt"
        return None

    @classmethod
    async def _fetch_pairs_map(cls) -> dict[tuple[str, str], int]:
        """Build a mapping of (quote_symbol, base_symbol) -> pair_id."""
        try:
            data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return {}

        if data.get("status") != 0:
            return {}

        market_map = {}
        for market in data.get("data", []):
            quote_sym = market["quote_currency_symbol"]["en"].lower()
            base_sym = market["base_currency_symbol"]["en"].upper()
            market_map[(quote_sym, base_sym)] = market["pair_id"]

        return market_map

    @classmethod
    def _parse_otc_market(cls, market: dict, quote: Quote, bases: list[Base]) -> Coin | None:
        buy_price = market.get("buy")
        sell_price = market.get("sell")

        if buy_price in (None, "", "-") or sell_price in (None, "", "-"):
            return None

        base_str = market["base_currency_symbol"]["en"].upper()
        try:
            base = Base(base_str)
        except ValueError:
            return None

        if base not in bases:
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=Decimal(str(buy_price)) / 10,
            raw_sell_price=Decimal(str(sell_price)) / 10,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        try:
            pairs_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        if pairs_data.get("status") != 0:
            return Coins()

        result = Coins()

        for quote in quotes:
            currency_string = cls._get_quote_string(quote)
            if currency_string is None:
                continue

            for market in pairs_data["data"]:
                if market["quote_currency_symbol"]["en"] != currency_string:
                    continue

                coin = cls._parse_otc_market(market, quote, bases)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    def _build_order_list(cls, entries: list, q: Quote, b: Base, now: datetime.datetime) -> list[Order]:
        orders = []

        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue

            try:
                price = cls._clean_number(entry[0]) / 10
                amount = cls._clean_number(entry[1])
            except (ValueError, TypeError):
                continue

            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                raw_buy_price=price,
                raw_sell_price=price,
                buy_fee=Decimal(0.25),
                sell_fee=Decimal(0.25),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount))

        return orders

    @classmethod
    async def _fetch_single_orderbook(cls, semaphore: asyncio.Semaphore, pid: int, b: Base, q: Quote):
        async with semaphore:
            try:
                buys_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pid}/buys"
                sells_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pid}/sells"
                buys_data, sells_data = await asyncio.gather(get_json(buys_url), get_json(sells_url))
            except (OSError, ValueError, TimeoutError):
                return None

            if buys_data.get("status") != 0 or sells_data.get("status") != 0:
                return None

            bids_raw = buys_data.get("data", [])
            asks_raw = sells_data.get("data", [])

            if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
                return None

            now = datetime.datetime.now(datetime.timezone.utc)
            bids_list = cls._build_order_list(bids_raw, q, b, now)
            asks_list = cls._build_order_list(asks_raw, q, b, now)

            if not bids_list and not asks_list:
                return None

            return (q, b), OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        market_map = await cls._fetch_pairs_map()
        if not market_map:
            return OrderBooks()

        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            quote_symbol = cls._get_quote_string(quote)
            if quote_symbol is None:
                continue

            for base in bases:
                pair_id = market_map.get((quote_symbol, base.value.upper()))
                if pair_id is not None:
                    tasks.append(cls._fetch_single_orderbook(semaphore, pair_id, base, quote))

        results = await asyncio.gather(*tasks)
        final_result = OrderBooks()

        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)

        return final_result
