import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class TabdealProvider:
    provider_name = ProviderName.TABDEAL

    @classmethod
    async def get_otc(cls, _quotes: list[Quote], _bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        """Map Quote enum to Tabdeal currency code and multiplier."""
        if quote == Quote.RLS:
            return "IRT", 1
        elif quote == Quote.USD:
            return "USDT", 1
        return None

    @classmethod
    def _build_order_list(cls, entries: list, mult: int, q: Quote, b: Base, now: datetime.datetime, reverse: bool = False) -> list[Order]:
        """Build Order list from price/amount entries."""
        orders = []
        for entry in entries:
            price = Decimal(str(entry["price"])) * mult
            amount = Decimal(str(entry["amount"]))
            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                buy_price=price,
                sell_price=price,
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount))

        # Sort: asks ascending (lowest first), bids descending (highest first)
        orders.sort(key=lambda x: x.coin.sell_price, reverse=reverse)
        return orders

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """Fetch P2P order book from Tabdeal."""
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(q: Quote, b: Base, to_curr: str, mult: int):
            from_curr = b.value
            url = "https://api-web.tabdeal.org/r/swap/prices_zero_commission_tier_based/"

            async with semaphore:
                try:
                    data = await get_json(url, {"from_currency": from_curr, "to_currency": to_curr})
                except (OSError, ValueError, TimeoutError):
                    return None

                from_data = data.get("from_amount_data", [])
                to_data = data.get("to_amount_data", [])

                if not from_data and not to_data:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)
                asks_list = cls._build_order_list(from_data, mult, q, b, now, reverse=False)
                bids_list = cls._build_order_list(to_data, mult, q, b, now, reverse=True)

                return (q, b), OrderBook(asks=asks_list, bids=bids_list)

        tasks = []
        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if not mapping:
                continue

            to_currency, multiplier = mapping
            for base in bases:
                tasks.append(fetch_pair(quote, base, to_currency, multiplier))

        results = await asyncio.gather(*tasks)

        for result_item in results:
            if result_item is not None:
                _, orderbook = result_item
                result.upsert(orderbook)

        return result