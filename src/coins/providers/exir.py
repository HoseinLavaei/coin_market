import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, OrderBook, Order


class ExirProvider:
    """Fetches OTC and order book data from Exir exchange."""
    provider_name = ProviderName.EXIR

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """
        Fetch OTC prices from Exir.
        Endpoint: https://api.exir.io/v2/oracle/prices?amount=1&quote=irt&assets=usdt
        Response: {"usdt": 188361000}
        """
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base):
            # Map quote to Exir's format
            quote_str = "irt" if quote == Quote.TMN else "usdt" if quote == Quote.USD else None
            if quote_str is None:
                return None

            # Map base to Exir's format (lowercase)
            base_str = base.value.lower()

            params = {
                "amount": "1",
                "quote": quote_str,
                "assets": base_str,
            }

            async with semaphore:
                try:
                    data = await get_json("https://api.exir.io/v2/oracle/prices", params=params)
                except (OSError, ValueError, TimeoutError):
                    return None

                # Response is like: {"usdt": 188361000}
                # The key is the asset name, the value is the price in the quote currency (IRT or USD)
                price_value = data.get(base_str)
                if price_value is None:
                    return None

                # The price returned is in the quote currency (e.g., IRT for 1 USDT)
                # For buy and sell, we use the same price (or adjust if Exir has spread)
                price = Decimal(str(price_value))

                the_coin = Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=price,
                    raw_sell_price=price,
                    buy_fee=Decimal("0.12"),
                    sell_fee=Decimal("0.12"),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                return (quote, base), the_coin

        tasks = [fetch_otc(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(2)

        def build_orders(prices_data: list, quote: Quote, base: Base, now: datetime.datetime) -> list[Order]:
            return [
                Order(
                    coin=Coin(
                        provider=cls.provider_name,
                        base=base,
                        quote=quote,
                        raw_buy_price=Decimal(str(price)),
                        raw_sell_price=Decimal(str(price)),
                        buy_fee=Decimal("0.35"),
                        sell_fee=Decimal("0.35"),
                        timestamp=now,
                    ),
                    quantity=Decimal(str(amount)),
                )
                for price, amount in prices_data
            ]

        async def fetch_pair(quote: Quote, base: Base):
            quote_str = "irt" if quote == Quote.TMN else "usdt" if quote == Quote.USD else None
            if quote_str is None:
                return None

            pair_name = f"{base.value.lower()}-{quote_str}"

            async with semaphore:
                data = await get_json("https://api.exir.io/v2/orderbook", params={"symbol": pair_name})

                if pair_name not in data:
                    return None

                order_data = data.get(pair_name)
                if not order_data or not isinstance(order_data, dict):
                    return None

                bids_raw = order_data.get("bids", [])
                asks_raw = order_data.get("asks", [])

                if not bids_raw and not asks_raw:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)
                return (quote, base), OrderBook(
                    asks=build_orders(asks_raw, quote, base, now),
                    bids=build_orders(bids_raw, quote, base, now),
                )
        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
