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
                        _buy_price=Decimal(str(price)) * multiplier,
                        _sell_price=Decimal(str(price)) * multiplier,
                        buy_fee=Decimal('0.35'),
                        sell_fee=Decimal('0.35'),
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
                return None

            pair_name = f"{base.value.lower()}-{quote_str}"

            async with semaphore:
                try:
                    json_data = await get_json(
                        "https://api.exir.io/v2/orderbook",
                        params={"symbol": pair_name}
                    )

                    # Check if the response contains the expected key
                    if pair_name not in json_data:
                        print(f"Exir: No data for symbol '{pair_name}'. Available keys: {list(json_data.keys())}")
                        return None

                    data = json_data.get(pair_name)
                    if not data or not isinstance(data, dict):
                        print(f"Exir: Invalid data for symbol '{pair_name}': {data}")
                        return None

                    bids_raw = data.get("bids", [])
                    asks_raw = data.get("asks", [])

                    # If both sides are empty, the pair exists but has no liquidity
                    if not bids_raw and not asks_raw:
                        print(f"Exir: Symbol '{pair_name}' has empty orderbook")
                        return None

                    now = datetime.datetime.now(datetime.timezone.utc)
                    bids_list = build_orders(bids_raw, multiplier, quote, base, now)
                    asks_list = build_orders(asks_raw, multiplier, quote, base, now)

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(f"Exir: Error fetching orderbook for {pair_name}: {e}")
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
