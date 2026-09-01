import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class OkexProvider:
    """Fetches OTC and order book data from OK-EX exchange."""
    provider_name: ProviderName = ProviderName.OKEX

    @classmethod
    def _parse_otc_ticker(
            cls,
            ticker: dict[str, Any],
            base: Base,
            quote: Quote,
    ) -> Optional[Coin]:
        """Parse a single OTC ticker into a Coin, or None if invalid."""
        if ticker.get("asset") != base.value:
            return None

        buy_price = ticker.get("buyAmt")
        sell_price = ticker.get("sellAmt")
        if buy_price is None or sell_price is None:
            return None

        try:
            buy_dec = Decimal(str(buy_price))
            sell_dec = Decimal(str(sell_price))
        except (ValueError, TypeError):
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=buy_dec,
            raw_sell_price=sell_dec,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base) -> Optional[Coin]:
            async with semaphore:
                try:
                    data = await get_json("https://azapi.ok-ex.io/api/v1/asset/otc/tickers")
                except (OSError, ValueError, TimeoutError):
                    return None

                # The API returns a list of tickers
                tickers: list[dict[str, Any]] = data if isinstance(data, list) else []
                for ticker in tickers:
                    coin = cls._parse_otc_ticker(ticker, base, quote)
                    if coin:
                        return coin
                return None

        tasks = [fetch_otc(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for res_coin in results:
            if res_coin:
                result.upsert(res_coin)

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
                buy_fee=Decimal(0.1),
                sell_fee=Decimal(0.1),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount_dec))
        return orders

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(
                quote: Quote,
                base: Base,
        ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
            quote_str = "IRT" if quote == Quote.TMN else str(quote.value)
            symbol = f"{base.value}-{quote_str}"

            async with semaphore:
                try:
                    data = await get_json(
                        "https://sapi.ok-ex.io/api/v1/spot/public/books",
                        {"symbol": symbol, "limit": "20"},
                    )
                except (OSError, ValueError, TimeoutError):
                    return None

                bids_raw: list[list[Any]] = data.get("bids", [])
                asks_raw: list[list[Any]] = data.get("asks", [])
                if not bids_raw and not asks_raw:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)
                bids = cls._build_orders(bids_raw, quote, base, now)
                asks = cls._build_orders(asks_raw, quote, base, now)
                if not bids and not asks:
                    return None

                return (quote, base), OrderBook(asks=asks, bids=bids)

        tasks = [fetch_orderbook(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for item in results:
            if item is not None:
                _, orderbook = item
                result.upsert(orderbook)

        return result
