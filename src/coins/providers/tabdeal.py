import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class TabdealProvider:
    """Fetches OTC and order book data from Tabdeal exchange."""
    provider_name = ProviderName.TABDEAL

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> str | None:
        if quote == Quote.TMN:
            return "IRT"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    def _build_order_list(
            cls,
            entries: list,
            q: Quote,
            b: Base,
            now: datetime.datetime,
            reverse: bool = False,
    ) -> list[Order]:
        orders = []

        for entry in entries:
            price = Decimal(str(entry[0]))
            amount = Decimal(str(entry[1]))

            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                raw_buy_price=price,
                raw_sell_price=price,
                buy_fee=Decimal("0.35"),
                sell_fee=Decimal("0.35"),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount))

        orders.sort(key=lambda x: x.coin.sell_price, reverse=reverse)
        return orders

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(q: Quote, b: Base):
            # Build symbol from base and quote
            quote_mapping = cls._get_quote_mapping(q)
            if quote_mapping is None:
                return None
            quote_str = quote_mapping
            symbol = f"{b.value}{quote_str}"
            url = "https://api1.tabdeal.org/r/api/v1/depth"
            params = {"symbol": symbol}

            async with semaphore:
                try:
                    data = await get_json(url, params=params)
                except (OSError, ValueError, TimeoutError):
                    return None

                asks_raw = data.get("asks", [])
                bids_raw = data.get("bids", [])

                if not asks_raw and not bids_raw:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)

                return (q, b), OrderBook(
                    asks=cls._build_order_list(asks_raw, q, b, now, reverse=False),
                    bids=cls._build_order_list(bids_raw, q, b, now, reverse=True),
                )

        tasks = []
        for quote in quotes:
            for base in bases:
                tasks.append(fetch_pair(quote, base))

        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
