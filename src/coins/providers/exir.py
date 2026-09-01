import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, OrderBook, Order


class ExirProvider:
    """Fetches OTC and order book data from Exir exchange."""
    provider_name: ProviderName = ProviderName.EXIR

    @classmethod
    def _get_quote_string(cls, quote: Quote) -> Optional[str]:
        """Map Quote to Exir's API format."""
        if quote == Quote.TMN:
            return "irt"
        if quote == Quote.USD:
            return "usdt"
        return None

    @classmethod
    def _parse_otc_response(
            cls,
            data: dict[str, Any],
            quote: Quote,
            base: Base,
    ) -> Optional[Coin]:
        """Parse the OTC response into a Coin, or None if invalid."""
        base_str = base.value.lower()
        price_value = data.get(base_str)
        if price_value is None:
            return None
        try:
            price = Decimal(str(price_value))
        except (ValueError, TypeError):
            return None
        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=price,
            raw_sell_price=price,
            buy_fee=Decimal("0.12"),
            sell_fee=Decimal("0.12"),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base) -> Optional[Coin]:
            quote_str = cls._get_quote_string(quote)
            if quote_str is None:
                return None
            params = {
                "amount": "1",
                "quote": quote_str,
                "assets": base.value.lower(),
            }
            async with semaphore:
                try:
                    data = await get_json("https://api.exir.io/v2/oracle/prices", params=params)
                except (OSError, ValueError, TimeoutError):
                    return None
                return cls._parse_otc_response(data, quote, base)

        tasks = [fetch_otc(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for coin in results:
            if coin:
                result.upsert(coin)

        return result

    @classmethod
    def _build_orders(
            cls,
            prices_data: list[list[Any]],
            quote: Quote,
            base: Base,
            now: datetime.datetime,
    ) -> list[Order]:
        """Build a list of Order objects from raw price/amount pairs."""
        orders: list[Order] = []
        for price, amount in prices_data:
            try:
                price_dec = Decimal(str(price))
                amount_dec = Decimal(str(amount))
            except (ValueError, TypeError):
                continue
            coin = Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
                raw_buy_price=price_dec,
                raw_sell_price=price_dec,
                buy_fee=Decimal("0.35"),
                sell_fee=Decimal("0.35"),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount_dec))
        return orders

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(2)

        async def fetch_pair(quote: Quote, base: Base) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
            quote_str = cls._get_quote_string(quote)
            if quote_str is None:
                return None
            pair_name = f"{base.value.lower()}-{quote_str}"

            async with semaphore:
                try:
                    data = await get_json("https://api.exir.io/v2/orderbook", params={"symbol": pair_name})
                except (OSError, ValueError, TimeoutError):
                    return None

                order_data = data.get(pair_name)
                if not order_data or not isinstance(order_data, dict):
                    return None

                bids_raw: list[list[Any]] = order_data.get("bids", [])
                asks_raw: list[list[Any]] = order_data.get("asks", [])
                if not bids_raw and not asks_raw:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)
                bids = cls._build_orders(bids_raw, quote, base, now)
                asks = cls._build_orders(asks_raw, quote, base, now)
                if not bids and not asks:
                    return None
                return (quote, base), OrderBook(asks=asks, bids=bids)

        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for item in results:
            if item is not None:
                _, orderbook = item
                result.upsert(orderbook)

        return result
