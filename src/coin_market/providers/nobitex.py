import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class NobitexProvider:
    provider_name = ProviderName.NOBITEX
    """Nobitex exchange API provider."""

    @classmethod
    def _parse_market_data(cls, market_key: str, market_data: dict, bases: list[Base], quote: Quote) -> Coin | None:
        """Parse a single market entry and return a Coin if valid, else None."""
        base_str = market_key.split("-")[0].upper()
        try:
            base = Base(base_str)
        except ValueError:
            return None

        if base not in bases:
            return None

        try:
            buy_price = Decimal(str(market_data["bestBuy"]))
            sell_price = Decimal(str(market_data["bestSell"]))
        except (KeyError, ValueError):
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            buy_price=buy_price,
            sell_price=sell_price,
            quote=quote,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result: Coins = Coins()
        for quote in quotes:
            currency_string = "rls" if quote == Quote.RLS else "usdt"
            params = {
                "srcCurrency": ",".join(str(b.value).lower() for b in bases),
                "dstCurrency": currency_string,
            }
            
            try:
                json_data = await get_json("https://apiv2.nobitex.ir/market/stats", params)
            except (OSError, ValueError, TimeoutError):
                continue

            if json_data.get("status") != "ok":
                continue

            stats = json_data.get("stats", {})
            for market_key, market_data in stats.items():
                coin = cls._parse_market_data(market_key, market_data, bases, quote)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(quote: Quote, base: Base):
            # Map quote to Nobitex's currency string
            quote_str = "IRT" if quote == Quote.RLS else "USDT"
            pair = f"{base.value}{quote_str}"  # e.g., "BTCIRT" or "BTCUSDT"

            async with semaphore:
                try:
                    url = f"https://apiv2.nobitex.ir/v3/orderbook/{pair}"
                    data = await get_json(url)

                    if data.get("status") != "ok":
                        return None

                    bids_raw = data.get("bids", [])  # list of [price, amount]
                    asks_raw = data.get("asks", [])  # list of [price, amount]
                    now = datetime.datetime.now(datetime.timezone.utc)

                    # ---- Build BIDS list ----
                    # For each bid, both buy_price and sell_price are set to the bid price.
                    # get_by_volume uses coin.buy_price when consuming bids.
                    bids_list = [
                        Order(
                            coin=Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)),
                                sell_price=Decimal(str(price)),
                                timestamp=now,
                            ),
                            quantity=Decimal(str(amount)),
                        )
                        for price, amount in bids_raw
                    ]

                    # ---- Build ASKS list ----
                    # For each ask, both prices are set to the ask price.
                    # get_by_volume uses coin.sell_price when consuming asks.
                    asks_list = [
                        Order(
                            coin=Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)),
                                sell_price=Decimal(str(price)),
                                timestamp=now,
                            ),
                            quantity=Decimal(str(amount)),
                        )
                        for price, amount in asks_raw
                    ]

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(f"Cant get nobitex's Orderbook:{e}")
                    # Optionally log the error here
                    return None

        # Build all tasks
        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]

        # Run all fetch tasks concurrently
        results = await asyncio.gather(*tasks)

        # Aggregate successful results
        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result