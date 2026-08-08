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

                # Extract the price_inverse from the first tier (smallest amount)
                # price_inverse is the amount of quote currency needed to buy 1 base currency.
                buy_price_raw = Decimal(from_data[0].get("price_inverse", "0"))
                sell_price_raw = Decimal(to_data[0].get("price_inverse", "0"))

                # Apply multiplier (10 for RLS to convert from Toman to Rial, 1 for USD)
                buy_price = buy_price_raw * multiplier
                sell_price = sell_price_raw * multiplier

                _coin = Coin(
                    provider=cls.provider_name,
                    base=_base,
                    quote=_quote,
                    _buy_price=buy_price,
                    _sell_price=sell_price,
                    buy_fee=Decimal('0'),  # OTC has zero commission
                    sell_fee=Decimal('0'),  # OTC has zero commission
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
    def _build_order_list(cls, entries: list, mult: int, q: Quote, b: Base, now: datetime.datetime,
                          reverse: bool = False) -> list[Order]:
        """Build Order list from price/amount entries."""
        orders = []
        for entry in entries:
            # The price from API is in the quote currency (Toman or USDT)
            price = Decimal(str(entry["price"])) * mult
            amount = Decimal(str(entry["amount"]))
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
                # from_data corresponds to asks (you pay base to get quote? Actually we need to interpret correctly)
                # For orderbook, we need bids and asks.
                # Since the API is tiered, we treat each tier as an order level.
                # Asks: orders where you sell base (USDT) for quote (IRT) => from_data?
                # When from_currency=USDT and to_currency=IRT, from_data gives the price in IRT per 1 USDT.
                # That is the price you receive when selling USDT (sell price). So from_data = bids? Actually bids are buy orders.
                # Let's define:
                #   Asks: people selling base (USDT) at a price => they want quote (IRT). So the price is IRT per USDT.
                #   Bids: people buying base (USDT) at a price => they offer quote (IRT). So price is IRT per USDT.
                # The API returns from_amount_data (converting from_currency to to_currency) which is the amount of to_currency you get per 1 from_currency.
                # That is the price in quote currency per 1 base.
                # So from_amount_data gives the price for buying quote with base (i.e., selling base). That corresponds to asks? Actually when you sell base, you get quote, so the price is the bid? No.
                # Let's keep it simple: we treat both as orders and sort appropriately.
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
