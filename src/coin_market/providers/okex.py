import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks
from ..provider_name import ProviderName


class OkexProvider:
    provider_name = ProviderName.OKEX

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
                quote_str = "USDT"
                multiplier = 1
            elif quote == Quote.RLS:
                quote_str = "IRT"
                multiplier = 10
            else:
                return None

            url = "https://azapi.ok-ex.io/api/v1/asset/otc/tickers"

            async with semaphore:
                try:
                    data = await get_json(url)

                    # Response is a list of ticker objects
                    # Find the ticker for the specific asset
                    for ticker in data:
                        if ticker.get("asset") == base.value:
                            buy_price = ticker.get("buyAmt")
                            sell_price = ticker.get("sellAmt")

                            if buy_price is None or sell_price is None:
                                return None

                            coin = Coin(
                                provider=cls.provider_name,
                                base=base,
                                buy_price=Decimal(str(buy_price)) * multiplier,
                                sell_price=Decimal(str(sell_price)) * multiplier,
                                quote=quote,
                                timestamp=datetime.datetime.now(datetime.timezone.utc),
                            )
                            return (quote, base), coin

                    return None  # Asset not found

                except Exception:
                    return None

        # Build tasks for all requested pairs
        tasks = []
        for quote in quotes:
            for base in bases:
                tasks.append(fetch_otc(quote, base))

        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

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

                    bids_raw = data.get("bids", [])  # list of [price, amount]
                    asks_raw = data.get("asks", [])  # list of [price, amount]
                    now = datetime.datetime.now(datetime.timezone.utc)

                    # Multiplier: 10 for RLS (IRT), 1 for USD (USDT)
                    multiplier = 10 if quote == Quote.RLS else 1

                    # ---- Build BIDS list ----
                    bids_list = [
                        (
                            Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)) * multiplier,
                                sell_price=Decimal(str(price)) * multiplier,
                                timestamp=now,
                            ),
                            Decimal(str(amount)),
                        )
                        for price, amount in bids_raw
                    ]

                    # ---- Build ASKS list ----
                    asks_list = [
                        (
                            Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)) * multiplier,
                                sell_price=Decimal(str(price)) * multiplier,
                                timestamp=now,
                            ),
                            Decimal(str(amount)),
                        )
                        for price, amount in asks_raw
                    ]

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(e)
                    return None

        # Build tasks for all requested pairs
        tasks = []
        for quote in quotes:
            for base in bases:
                tasks.append(fetch_orderbook(quote, base))

        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result