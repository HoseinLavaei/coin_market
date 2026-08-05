import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class ExirProvider:
    provider_name = ProviderName.EXIR
    """Exir exchange API provider."""

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch order books from Exir for the given quote/base pairs.
        Uses the public /v2/orderbook endpoint.
        """
        pairs = [(quote, base) for quote in quotes for base in bases]
        semaphore = asyncio.Semaphore(2)
        result = OrderBooks()

        def build_orders(prices_data: list, multiplier: int, quote: Quote, base: Base, now: datetime.datetime) -> list[
            Order]:
            """Build Order objects from price/amount pairs."""
            return [
                Order(
                    coin=Coin(
                        provider=cls.provider_name,
                        base=base,
                        quote=quote,
                        buy_price=Decimal(str(price)) * multiplier,
                        sell_price=Decimal(str(price)) * multiplier,
                        timestamp=now,
                    ),
                    quantity=Decimal(str(amount)),
                )
                for price, amount in prices_data
            ]

        async def fetch_pair(quote: Quote, base: Base):
            # Map quote to Exir's currency string and multiplier
            if quote == Quote.RLS:
                quote_str = "irt"
                multiplier = 10
            elif quote == Quote.USD:
                quote_str = "usdt"
                multiplier = 1
            else:
                return None  # Unsupported quote

            pair_name = f"{base.value.lower()}-{quote_str}"  # e.g., "btc-usdt"

            async with semaphore:
                try:
                    json_data = await get_json(
                        "https://api.exir.io/v2/orderbook",
                        params={"symbol": pair_name}
                    )
                    data = json_data.get(pair_name)
                    if not data or not isinstance(data, dict):
                        return None

                    bids_raw = data.get("bids", [])  # list of [price, amount]
                    asks_raw = data.get("asks", [])  # list of [price, amount]
                    now = datetime.datetime.now(datetime.timezone.utc)

                    bids_list = build_orders(bids_raw, multiplier, quote, base, now)
                    asks_list = build_orders(asks_raw, multiplier, quote, base, now)

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(f"Cant get exir's Orderbook:{e}")
                    return None

        # Run all fetch tasks concurrently
        tasks = [fetch_pair(quote, base) for quote, base in pairs]
        results = await asyncio.gather(*tasks)

        # Aggregate successful results
        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
