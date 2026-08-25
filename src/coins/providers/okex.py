import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class OkexProvider:
    """Fetches OTC and order book data from OK-EX exchange."""
    provider_name = ProviderName.OKEX

    @classmethod
    def _parse_otc_ticker(cls, ticker: dict, base: Base, quote: Quote) -> Coin | None:
        if ticker.get("asset") != base.value:
            return None

        buy_price = ticker.get("buyAmt")
        sell_price = ticker.get("sellAmt")

        if buy_price is None or sell_price is None:
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=Decimal(str(buy_price)),
            raw_sell_price=Decimal(str(sell_price)),
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base):
            async with semaphore:
                try:
                    data = await get_json("https://azapi.ok-ex.io/api/v1/asset/otc/tickers")
                except (OSError, ValueError, TimeoutError):
                    return None

                for ticker in data:
                    this_coin = cls._parse_otc_ticker(ticker, base, quote)
                    if this_coin:
                        return (quote, base), this_coin

                return None

        tasks = [fetch_otc(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

    @classmethod
    def _build_orders(cls, prices_data: list, quote: Quote, base: Base, now: datetime.datetime) -> list[Order]:
        return [
            Order(
                coin=Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=Decimal(str(price)),
                    raw_sell_price=Decimal(str(price)),
                    buy_fee=Decimal(0.1),
                    sell_fee=Decimal(0.1),
                    timestamp=now,
                ),
                quantity=Decimal(str(amount)),
            )
            for price, amount in prices_data
        ]

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(quote: Quote, base: Base):
            symbol = f"{base.value}-{"IRT" if quote == Quote.TMN else str(quote.value)}"

            async with semaphore:
                try:
                    data = await get_json(
                        "https://sapi.ok-ex.io/api/v1/spot/public/books",
                        {"symbol": symbol, "limit": "20"},
                    )
                except (OSError, ValueError, TimeoutError):
                    return None

                bids_raw = data.get("bids", [])
                asks_raw = data.get("asks", [])
                now = datetime.datetime.now(datetime.timezone.utc)

                return (quote, base), OrderBook(
                    asks=cls._build_orders(asks_raw, quote, base, now),
                    bids=cls._build_orders(bids_raw, quote, base, now),
                )

        tasks = [fetch_orderbook(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
