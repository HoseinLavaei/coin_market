import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ...domain import Coin, Quote, Base, Coins, OrderBooks, ProviderName, Order, OrderBook


class ExirProvider:
    """Fetches order book data from Exir exchange. OTC is not supported."""
    provider_name = ProviderName.EXIR

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

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
                try:
                    data = await get_json("https://api.exir.io/v2/orderbook", params={"symbol": pair_name})

                    if pair_name not in data:
                        print(f"Exir: No data for symbol '{pair_name}'")
                        return None

                    order_data = data.get(pair_name)
                    if not order_data or not isinstance(order_data, dict):
                        print(f"Exir: Invalid data for '{pair_name}'")
                        return None

                    bids_raw = order_data.get("bids", [])
                    asks_raw = order_data.get("asks", [])

                    if not bids_raw and not asks_raw:
                        print(f"Exir: Empty orderbook for '{pair_name}'")
                        return None

                    now = datetime.datetime.now(datetime.timezone.utc)
                    return (quote, base), OrderBook(
                        asks=build_orders(asks_raw, quote, base, now),
                        bids=build_orders(bids_raw, quote, base, now),
                    )

                except Exception as e:
                    print(f"Exir: Error fetching orderbook for {pair_name}: {e}")
                    return None

        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
