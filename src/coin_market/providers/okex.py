import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class OkexProvider:
    provider_name = ProviderName.OKEX

    @classmethod
    def _parse_otc_ticker(cls, ticker: dict, base: Base, quote: Quote, multiplier: int) -> Coin | None:
        """Parse OTC ticker and return Coin if valid, else None."""
        if ticker.get("asset") != base.value:
            return None

        buy_price = ticker.get("buyAmt")
        sell_price = ticker.get("sellAmt")

        if buy_price is None or sell_price is None:
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            buy_price=Decimal(str(buy_price)) * multiplier,
            sell_price=Decimal(str(sell_price)) * multiplier,
            quote=quote,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """
        Fetch OTC prices from OK-EX.
        Uses /api/v1/asset/otc/tickers endpoint.
        """
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base):
            # Map quote to OK-EX currency code
            if quote == Quote.USD:
                multiplier = 1
            elif quote == Quote.RLS:
                multiplier = 10
            else:
                return None

            url = "https://azapi.ok-ex.io/api/v1/asset/otc/tickers"

            async with semaphore:
                try:
                    data = await get_json(url)
                except (OSError, ValueError, TimeoutError):
                    return None

                # Response is a list of ticker objects
                for ticker in data:
                    the_coin = cls._parse_otc_ticker(ticker, base, quote, multiplier)
                    if the_coin:
                        return (quote, base), the_coin

                return None  # Asset not found

        # Build tasks for all requested pairs
        tasks = [fetch_otc(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for result_item in results:
            if result_item is not None:
                _, coin = result_item
                result.upsert(coin)

        return result

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
                    buy_price=Decimal(str(price)) * multiplier,
                    sell_price=Decimal(str(price)) * multiplier,
                    timestamp=now,
                ),
                quantity=Decimal(str(amount)),
            )
            for price, amount in prices_data
        ]

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch P2P order books from OK-EX.
        Uses /api/v1/spot/public/books endpoint.
        """
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(quote: Quote, base: Base):
            # Map to OK-EX symbol format: e.g., "USDT-IRT"
            symbol = f"{base.value}-{"IRT" if quote == Quote.RLS else str(quote.value)}"
            url = "https://sapi.ok-ex.io/api/v1/spot/public/books"

            async with semaphore:
                try:
                    data = await get_json(url, {"symbol": symbol, "limit": "20"})
                except (OSError, ValueError, TimeoutError):
                    return None

                bids_raw = data.get("bids", [])  # list of [price, amount]
                asks_raw = data.get("asks", [])  # list of [price, amount]
                now = datetime.datetime.now(datetime.timezone.utc)

                # Multiplier: 10 for RLS (IRT), 1 for USD (USDT)
                multiplier = 10 if quote == Quote.RLS else 1

                bids_list = cls._build_orders(bids_raw, multiplier, quote, base, now)
                asks_list = cls._build_orders(asks_raw, multiplier, quote, base, now)

                return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

        # Build tasks for all requested pairs
        tasks = [fetch_orderbook(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for result_item in results:
            if result_item is not None:
                _, orderbook = result_item
                result.upsert(orderbook)

        return result
