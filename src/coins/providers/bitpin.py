import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class BitpinProvider:
    """Fetches OTC and order book data from Bitpin exchange."""
    provider_name: ProviderName = ProviderName.BITPIN

    @classmethod
    def _get_quote_string(cls, quote: Quote) -> Optional[str]:
        if quote == Quote.TMN:
            return "IRT"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    def _parse_otc_market(
            cls,
            market: dict[str, Any],
            quote: Quote,
            base: Base,
    ) -> Optional[Coin]:
        """Parse a single market entry into a Coin, or None if invalid."""
        try:
            price = Decimal(str(market["price"]))
            buy_percent = Decimal(str(market.get("otc_buy_percent", "0")))
            sell_percent = Decimal(str(market.get("otc_sell_percent", "0")))
        except (KeyError, ValueError, TypeError):
            return None

        return Coin.new(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=price,
            raw_sell_price=price,
            buy_fee=Decimal(buy_percent),
            sell_fee=Decimal(sell_percent),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    def _find_otc_market(
            cls,
            markets: list[dict[str, Any]],
            quote: Quote,
            base: Base,
            quote_string: str,
    ) -> Optional[Coin]:
        """Find the matching OTC market and return a Coin, or None."""
        for market in markets:
            if market["currency2"]["code"].upper() != quote_string:
                continue
            if market["currency1"]["code"].upper() != str(base.value):
                continue
            return cls._parse_otc_market(market, quote, base)
        return None

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        data = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets: list[dict[str, Any]] = data.get("results", [])
        result = Coins()

        for quote in quotes:
            quote_string = cls._get_quote_string(quote)
            if quote_string is None:
                continue
            for base in bases:
                coin = cls._find_otc_market(markets, quote, base, quote_string)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        market_map = await cls._build_market_map()
        if not market_map:
            return OrderBooks()

        tasks = []

        for quote in quotes:
            quote_string = cls._get_quote_string(quote)
            if quote_string is None:
                continue

            for base in bases:
                market_id = market_map.get((quote_string, base.value))
                if market_id is not None:
                    tasks.append(
                        cls._fetch_orderbook(market_id, base, quote)
                    )

        results = await asyncio.gather(*tasks)
        final_result = OrderBooks()

        for item in results:
            if item is not None:
                _, orderbook = item
                final_result.upsert(orderbook)

        return final_result

    @classmethod
    async def _build_market_map(cls) -> dict[tuple[str, str], int]:
        data = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets: list[dict[str, Any]] = data.get("results", [])

        market_map: dict[tuple[str, str], int] = {}
        for market in markets:
            quote_code = market["currency2"]["code"].upper()
            base_code = market["currency1"]["code"].upper()
            market_map[(quote_code, base_code)] = market["id"]

        return market_map

    @classmethod
    async def _fetch_orderbook(
            cls,
            market_id: int,
            base: Base,
            quote: Quote,
    ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
        url = f"https://api.bitpin.ir/v4/mth/orderbook/{market_id}/"
        data = await get_json(url)

        bids_raw: list[list[Any]] = data.get("bids", [])
        asks_raw: list[list[Any]] = data.get("asks", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        def build_orders(raw: list[list[Any]]) -> list[Order]:
            orders = []
            for price, amount in raw:
                try:
                    price_dec = Decimal(str(price))
                    amount_dec = Decimal(str(amount))
                except (ValueError, TypeError):
                    continue
                coin = Coin.new(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=price_dec,
                    raw_sell_price=price_dec,
                    buy_fee=Decimal(0.35),
                    sell_fee=Decimal(0.35),
                    timestamp=now,
                )
                if coin:
                    order = Order.new(coin=coin, quantity=amount_dec)
                    if order:
                        orders.append(order)
            return orders

        bids = build_orders(bids_raw)
        asks = build_orders(asks_raw)
        if not bids and not asks:
            return None

        orderbook = OrderBook.new(asks=asks, bids=bids)
        if orderbook is None:
            return None
        return (quote, base), orderbook