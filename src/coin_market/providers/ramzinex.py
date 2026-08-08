import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class RamzinexProvider:
    """Ramzinex exchange API provider."""
    provider_name = ProviderName.RAMZINEX

    @staticmethod
    def _clean_number(raw_value):
        """Remove commas and convert to Decimal safely."""
        if isinstance(raw_value, (int, float)):
            return Decimal(raw_value)
        if isinstance(raw_value, str):
            cleaned = raw_value.replace(",", "").strip()
            return Decimal(cleaned)
        raise ValueError(f"Unsupported type: {type(raw_value)}")

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        """Map Quote enum to Ramzinex currency symbol and multiplier."""
        if quote == Quote.RLS:
            return "irr", 10
        elif quote == Quote.USD:
            return "usdt", 1
        return None

    @classmethod
    async def _fetch_pairs_map(cls) -> dict:
        """Fetch pairs and build market map."""
        try:
            pairs_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return {}

        if pairs_data.get("status") != 0:
            return {}

        market_map = {}
        for market in pairs_data.get("data", []):
            quote_sym = market["quote_currency_symbol"]["en"].lower()
            base_sym = market["base_currency_symbol"]["en"].upper()
            market_map[(quote_sym, base_sym)] = market["pair_id"]

        return market_map

    @classmethod
    def _parse_otc_market(cls, market: dict, quote: Quote, bases: list[Base], multiplier: int) -> Coin | None:
        """Parse single OTC market entry and return Coin if valid, else None."""
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
            _buy_price=Decimal(str(buy_price)) * multiplier,
            _sell_price=Decimal(str(sell_price)) * multiplier,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            quote=quote,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """Fetch OTC prices from Ramzinex."""
        try:
            pairs_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        if pairs_data.get("status") != 0:
            return Coins()

        result = Coins()
        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if not mapping:
                continue

            currency_string, multiplier = mapping
            for market in pairs_data["data"]:
                if market["quote_currency_symbol"]["en"] != currency_string:
                    continue

                coin = cls._parse_otc_market(market, quote, bases, multiplier)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    def _build_order_list(cls, entries: list, mult: int, q: Quote, b: Base, now: datetime.datetime) -> list[Order]:
        """Build Order list from price/amount entries."""
        orders = []
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            try:
                price = cls._clean_number(entry[0]) * mult
                amount = cls._clean_number(entry[1])
            except (ValueError, TypeError):
                continue

            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                _buy_price=price,
                _sell_price=price,
                buy_fee=Decimal(0.25),
                sell_fee=Decimal(0.25),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount))

        return orders

    @classmethod
    async def _fetch_single_orderbook(cls, semaphore: asyncio.Semaphore, pid: int, b: Base, q: Quote, mult: int):
        """Fetch a single orderbook."""
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

            bids_list = cls._build_order_list(bids_raw, mult, q, b, now)
            asks_list = cls._build_order_list(asks_raw, mult, q, b, now)

            if not bids_list and not asks_list:
                return None

            return (q, b), OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """Fetch spot order books from Ramzinex."""
        market_map = await cls._fetch_pairs_map()
        if not market_map:
            return OrderBooks()

        semaphore = asyncio.Semaphore(5)
        tasks = []

        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if not mapping:
                continue

            quote_symbol, multiplier = mapping
            for base in bases:
                pair_id: int | None = market_map.get((quote_symbol, base.value.upper()))
                if pair_id is not None:
                    tasks.append(cls._fetch_single_orderbook(semaphore, pair_id, base, quote, multiplier))

        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for result_item in results:
            if result_item is not None:
                _, orderbook = result_item
                final_result.upsert(orderbook)

        return final_result
