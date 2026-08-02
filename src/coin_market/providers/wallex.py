import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class WallexProvider:
    """Wallex exchange API provider."""
    provider_name = ProviderName.WALLEX

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """
        Fetch OTC (over‑the‑counter) prices from Wallex.
        Uses the /v1/otc/markets endpoint to list available pairs,
        then fetches buy and sell prices concurrently with a semaphore.
        """
        # 1. Fetch available OTC markets
        json_data = await get_json("https://api.wallex.ir/v1/otc/markets")
        symbols = json_data.get("result", {})

        semaphore = asyncio.Semaphore(5)

        async def fetch_prices(symbol_name, base: Base, quote: Quote, multiplier):
            async with semaphore:
                try:
                    # Fetch buy and sell prices concurrently
                    buy_task = get_json(
                        "https://api.wallex.ir/v1/otc/price",
                        params={"symbol": symbol_name, "side": "BUY"}
                    )
                    sell_task = get_json(
                        "https://api.wallex.ir/v1/otc/price",
                        params={"symbol": symbol_name, "side": "SELL"}
                    )

                    buy_res, sell_res = await asyncio.gather(buy_task, sell_task)

                    if not buy_res.get("success") or not sell_res.get("success"):
                        return None

                    buy_price = Decimal(str(buy_res["result"]["price"]).rstrip("0").rstrip(",")) * multiplier
                    sell_price = Decimal(str(sell_res["result"]["price"]).rstrip("0").rstrip(",")) * multiplier

                    coin = Coin(
                        provider=cls.provider_name,
                        base=base,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        quote=quote,
                        timestamp=datetime.datetime.now(datetime.timezone.utc),
                    )
                    return (quote, base), coin

                except Exception:
                    return None

        # Build tasks
        tasks = []
        for quote in quotes:
            quote_string = "TMN" if quote == Quote.RLS else "USDT"
            multiplier = 10 if quote == Quote.RLS else 1
            for base in bases:
                symbol_name = f"{base.value}{quote_string}"
                if symbol_name in symbols:
                    tasks.append(fetch_prices(symbol_name, base, quote, multiplier))

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Aggregate results
        result = Coins()
        for r in results:
            if r is not None:
                _, coin = r
                result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch spot order books from Wallex.
        Uses the /v1/depth endpoint for each pair.
        Now fully concurrent with a semaphore.
        """
        # 1. Fetch available markets to validate pairs
        json_data = await get_json("https://api.wallex.ir/v1/markets")
        symbols = json_data.get("result", {}).get("symbols", {})

        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(market_key, base: Base, quote: Quote, multiplier):
            async with semaphore:
                try:
                    ob_data = await get_json(
                        "https://api.wallex.ir/v1/depth",
                        params={"symbol": market_key}
                    )
                    if not ob_data.get("success"):
                        return None

                    bids_raw = ob_data.get("result", {}).get("bid", [])  # list of {price, quantity}
                    asks_raw = ob_data.get("result", {}).get("ask", [])  # list of {price, quantity}
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
                                buy_price=Decimal(str(b["price"])) * multiplier,
                                sell_price=Decimal(str(b["price"])) * multiplier,
                                timestamp=now,
                            ),
                            quantity=Decimal(str(b["quantity"])),
                        )
                        for b in bids_raw
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
                                buy_price=Decimal(str(a["price"])) * multiplier,
                                sell_price=Decimal(str(a["price"])) * multiplier,
                                timestamp=now,
                            ),
                            quantity=Decimal(str(a["quantity"])),
                        )
                        for a in asks_raw
                    ]

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception:
                    return None

        # Build tasks
        tasks = []
        for quote in quotes:
            quote_string = "TMN" if quote == Quote.RLS else "USDT"
            multiplier = 10 if quote == Quote.RLS else 1
            for base in bases:
                market_key = f"{base.value}{quote_string}"
                # Check if the symbol exists in the market list
                if market_key in symbols:
                    # Optional: skip if stats["lastPrice"] is "-"
                    stats = symbols[market_key].get("stats", {})
                    if stats.get("lastPrice") == "-":
                        continue
                    tasks.append(fetch_orderbook(market_key, base, quote, multiplier))

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Aggregate results
        final_result = OrderBooks()
        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)

        return final_result