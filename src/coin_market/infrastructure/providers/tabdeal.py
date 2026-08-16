import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from ...domain import Coin, Quote, Base, Coins, OrderBooks, ProviderName, Order, OrderBook


class TabdealProvider:
    """Fetches OTC and order book data from Tabdeal exchange."""
    provider_name = ProviderName.TABDEAL

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        if quote == Quote.TMN:
            return "IRT", 1
        if quote == Quote.USD:
            return "USDT", 1
        return None

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(quote: Quote, base: Base):
            mapping = cls._get_quote_mapping(quote)
            if mapping is None:
                return None

            to_currency, _ = mapping
            params = {"from_currency": base.value, "to_currency": to_currency}

            async with semaphore:
                try:
                    data = await get_json(
                        "https://api-web.tabdeal.org/r/swap/prices_zero_commission_tier_based/",
                        params=params,
                    )
                except (OSError, ValueError, TimeoutError):
                    return None

                from_data = data.get("from_amount_data", [])
                to_data = data.get("to_amount_data", [])

                if not from_data or not to_data:
                    return None

                raw_buy_price = Decimal(from_data[0].get("price", "0"))
                raw_sell_price = Decimal(to_data[0].get("price", "0"))

                if raw_buy_price == Decimal(0) or raw_sell_price == Decimal(0):
                    return None

                this_coin = Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=raw_buy_price,
                    raw_sell_price=raw_sell_price,
                    buy_fee=Decimal("0"),
                    sell_fee=Decimal("0"),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                return (quote, base), this_coin

        tasks = [fetch_otc(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

    @classmethod
    def _build_order_list(
            cls,
            entries: list,
            q: Quote,
            b: Base,
            now: datetime.datetime,
            reverse: bool = False,
            amount_in_quote: bool = False,
    ) -> list[Order]:
        orders = []

        for entry in entries:
            price = Decimal(str(entry["price"]))
            amount_raw = Decimal(str(entry["amount"]))

            if amount_in_quote:
                amount = amount_raw / price if price != Decimal(0) else Decimal(0)
            else:
                amount = amount_raw

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

        async def fetch_pair(q: Quote, b: Base, to_curr: str):
            params = {"from_currency": b.value, "to_currency": to_curr}

            async with semaphore:
                try:
                    data = await get_json(
                        "https://api-web.tabdeal.org/r/swap/prices_zero_commission_tier_based/",
                        params=params,
                    )
                except (OSError, ValueError, TimeoutError):
                    return None

                from_data = data.get("from_amount_data", [])
                to_data = data.get("to_amount_data", [])

                if not from_data and not to_data:
                    return None

                now = datetime.datetime.now(datetime.timezone.utc)

                return (q, b), OrderBook(
                    asks=cls._build_order_list(from_data, q, b, now, reverse=False, amount_in_quote=False),
                    bids=cls._build_order_list(to_data, q, b, now, reverse=True, amount_in_quote=True),
                )

        tasks = []

        for quote in quotes:
            mapping = cls._get_quote_mapping(quote)
            if mapping is None:
                continue

            to_currency, _ = mapping

            for base in bases:
                tasks.append(fetch_pair(quote, base, to_currency))

        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
