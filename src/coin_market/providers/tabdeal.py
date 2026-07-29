import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks
from ..provider_name import ProviderName


class TabdealProvider:
    provider_name = ProviderName.TABDEAL

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch P2P order book from Tabdeal.
        API returns tier-based prices with amounts.
        """
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(quote: Quote, base: Base):
            # Map to Tabdeal's currency codes
            if quote == Quote.RLS:
                to_currency = "IRT"
                multiplier = 1  # API already returns IRT
            elif quote == Quote.USD:
                to_currency = "USDT"
                multiplier = 1
            else:
                return None  # Unsupported quote

            from_currency = base.value  # e.g., "BTC", "USDT"

            # Tabdeal only supports USDT pairs for now, but we keep the base flexible
            url = (
                f"https://api-web.tabdeal.org/r/swap/prices_zero_commission_tier_based/"
            )

            async with semaphore:
                try:
                    data = await get_json(url,{"from_currency":from_currency, "to_currency":to_currency})

                    # The API returns data even for unsupported pairs (empty arrays)
                    from_data = data.get("from_amount_data", [])
                    to_data = data.get("to_amount_data", [])

                    if not from_data and not to_data:
                        return None

                    now = datetime.datetime.now(datetime.timezone.utc)

                    # ---- Build ASKS (from_amount_data) ----
                    # Each entry: {"price": "192080", "amount": "50"}
                    # price = IRT per 1 USDT, amount = USDT available at that price
                    asks_list = []
                    for entry in from_data:
                        price = Decimal(str(entry["price"])) * multiplier
                        amount = Decimal(str(entry["amount"]))
                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            quote=quote,
                            buy_price=price,   # Both set to same price for order book
                            sell_price=price,  # get_by_volume uses sell_price for asks
                            timestamp=now,
                        )
                        asks_list.append((coin, amount))

                    # ---- Build BIDS (to_amount_data) ----
                    # Each entry: {"price": "192080", "amount": "9644999.999..."}
                    # price = IRT per 1 USDT, amount = IRT available at that price
                    # Convert IRT amount to USDT amount: usdt_amount = irt_amount / price
                    bids_list = []
                    for entry in to_data:
                        price = Decimal(str(entry["price"])) * multiplier
                        irt_amount = Decimal(str(entry["amount"]))
                        # Convert IRT amount to USDT amount
                        if price > 0:
                            usdt_amount = irt_amount / price
                        else:
                            continue
                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            quote=quote,
                            buy_price=price,   # Both set to same price for order book
                            sell_price=price,  # get_by_volume uses buy_price for bids
                            timestamp=now,
                        )
                        bids_list.append((coin, usdt_amount))

                    # Sort asks: lowest price first (standard)
                    asks_list.sort(key=lambda x: x[0].sell_price)
                    # Sort bids: highest price first (standard)
                    bids_list.sort(key=lambda x: x[0].buy_price, reverse=True)

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception:
                    return None

        # Build tasks for all requested pairs
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