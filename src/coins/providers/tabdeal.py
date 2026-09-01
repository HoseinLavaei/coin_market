import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class TabdealProvider:
    """Fetches OTC and order book data from Tabdeal exchange."""
    provider_name: ProviderName = ProviderName.TABDEAL

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> Optional[str]:
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
            entries: list[list[Any]],
            quote: Quote,
            base: Base,
            now: datetime.datetime,
            reverse: bool = False,
    ) -> list[Order]:
        orders: list[Order] = []
        for entry in entries:
            if len(entry) < 2:
                continue
            try:
                price = Decimal(str(entry[0]))
                amount = Decimal(str(entry[1]))
            except (ValueError, TypeError):
                continue

            coin = Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
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

        async def fetch_pair(
                quote: Quote,
                base: Base,
        ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
            quote_mapping = cls._get_quote_mapping(quote)
            if quote_mapping is None:
                return None
            symbol = f"{base.value}{quote_mapping}"
            url = "https://api1.tabdeal.org/r/api/v1/depth"
            params = {"symbol": symbol}

            async with semaphore:
                try:
                    data = await get_json(url, params=params)
                except (OSError, ValueError, TimeoutError):
                    return None

                asks_raw: list[list[Any]] = data.get("asks", [])
                bids_raw: list[list[Any]] = data.get("bids", [])
                if not asks_raw and not bids_raw:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)
                bids = cls._build_order_list(bids_raw, quote, base, now, reverse=True)
                asks = cls._build_order_list(asks_raw, quote, base, now, reverse=False)
                if not bids and not asks:
                    return None

                return (quote, base), OrderBook(asks=asks, bids=bids)

        tasks = [fetch_pair(q, b) for q in quotes for b in bases]
        results = await asyncio.gather(*tasks)

        for item in results:
            if item is not None:
                _, orderbook = item
                result.upsert(orderbook)

        return result
