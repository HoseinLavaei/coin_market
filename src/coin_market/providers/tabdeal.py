import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class TabdealProvider:
    provider_name = ProviderName.TABDEAL

    # ─── OTC ──────────────────────────────────────────────────────

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """
        Fetch OTC (Easy Buy/Sell) prices from Tabdeal.
        Uses /r/swap/prices_zero_commission_tier_based/ endpoint.
        """
        result = Coins()
        semaphore = asyncio.Semaphore(5)

        async def fetch_otc(_quote: Quote, _base: Base):
            mapping = cls._get_quote_mapping(_quote)
            if not mapping:
                return None

            to_currency, multiplier = mapping
            from_currency = _base.value  # e.g., USDT

            url = "https://api-web.tabdeal.org/r/swap/prices_zero_commission_tier_based/"
            params = {
                "from_currency": from_currency,
                "to_currency": to_currency
            }

            async with semaphore:
                try:
                    data = await get_json(url, params=params)
                except (OSError, ValueError, TimeoutError):
                    return None

                from_data = data.get("from_amount_data", [])
                to_data = data.get("to_amount_data", [])

                if not from_data or not to_data:
                    return None

                # The API returns price in the quote currency per 1 base (Toman per 1 USDT)
                # No inversion needed – just apply the multiplier.
                raw_buy_price = Decimal(from_data[0].get("price", "0"))
                raw_sell_price = Decimal(to_data[0].get("price", "0"))

                if raw_buy_price == Decimal(0) or raw_sell_price == Decimal(0):
                    return None

                buy_price = raw_buy_price * multiplier
                sell_price = raw_sell_price * multiplier

                _coin = Coin(
                    provider=cls.provider_name,
                    base=_base,
                    quote=_quote,
                    _buy_price=buy_price,
                    _sell_price=sell_price,
                    buy_fee=Decimal('0'),
                    sell_fee=Decimal('0'),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                return (_quote, _base), _coin

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

    # ─── OrderBook (P2P) ─────────────────────────────────────────

    @classmethod
    def _get_quote_mapping(cls, quote: Quote) -> tuple[str, int] | None:
        """Map Quote enum to Tabdeal currency code and multiplier."""
        if quote == Quote.RLS:
            return "IRT", 10  # API returns in Toman, we need Rial
        elif quote == Quote.USD:
            return "USDT", 1
        return None

    @classmethod
    def _build_order_list(
            cls,
            entries: list,
            mult: int,
            q: Quote,
            b: Base,
            now: datetime.datetime,
            reverse: bool = False,
            amount_in_quote: bool = False,
    ) -> list[Order]:
        """Build Order list from price/amount entries."""
        orders = []
        for entry in entries:
            price = Decimal(str(entry["price"])) * mult
            amount_raw = Decimal(str(entry["amount"]))

            if amount_in_quote:
                # Convert quote currency amount to base (USDT)
                if price != Decimal(0):
                    amount = amount_raw / price
                else:
                    amount = Decimal(0)
            else:
                amount = amount_raw

            coin = Coin(
                provider=cls.provider_name,
                base=b,
                quote=q,
                _buy_price=price,
                _sell_price=price,
                buy_fee=Decimal('0.35'),
                sell_fee=Decimal('0.35'),
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
            from_curr = b.value  # e.g., USDT
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

                # Asks: from_data gives prices and amounts in base currency (USDT)
                asks_list = cls._build_order_list(from_data, mult, q, b, now, reverse=False, amount_in_quote=False)

                # Bids: to_data gives prices, but amounts are in quote currency (IRT) – convert to USDT
                bids_list = cls._build_order_list(to_data, mult, q, b, now, reverse=True, amount_in_quote=True)

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
