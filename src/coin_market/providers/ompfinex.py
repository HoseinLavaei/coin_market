import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, OrderBook, Coins, OrderBooks
from ..provider_name import ProviderName


class OmpfinexProvider:
    provider_name = ProviderName.OMPFINEX

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        return Coins()

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch spot order books from Ompfinex.
        Uses /v1/market endpoint to get market IDs, then /v1/market/{id}/depth for order books.
        """
        # 1. Fetch all available markets
        markets_json = await get_json("https://api.ompfinex.com/v1/market")
        if markets_json.get("status") != "OK":
            return OrderBooks()

        # 2. Build market map: (quote_currency_id, base_currency_id) -> market_id
        market_map = {}
        for market in markets_json.get("data", []):
            quote_id = market["quote_currency"]["id"]  # e.g., "IRR"
            base_id = market["base_currency"]["id"]    # e.g., "USDT"
            market_map[(quote_id, base_id)] = market["id"]

        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(market_id: int, base: Base, quote: Quote, multiplier: int):
            async with semaphore:
                try:
                    data = await get_json(f"https://api.ompfinex.com/v1/market/{market_id}/depth", {"limit":"200"})

                    if data.get("status") != "OK":
                        return None

                    result_data = data.get("data", {})
                    bids_raw = result_data.get("bids", [])  # list of [price, amount]
                    asks_raw = result_data.get("asks", [])  # list of [price, amount]
                    now = datetime.datetime.now(datetime.timezone.utc)

                    # ---- Build BIDS list ----
                    bids_list = [
                        (
                            Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)) * multiplier,
                                sell_price=Decimal(str(price)) * multiplier,
                                timestamp=now,
                            ),
                            Decimal(str(amount)),
                        )
                        for price, amount in bids_raw
                    ]

                    # ---- Build ASKS list ----
                    asks_list = [
                        (
                            Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                buy_price=Decimal(str(price)) * multiplier,
                                sell_price=Decimal(str(price)) * multiplier,
                                timestamp=now,
                            ),
                            Decimal(str(amount)),
                        )
                        for price, amount in asks_raw
                    ]

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception:
                    return None

        # 3. Build tasks
        tasks = []
        for quote in quotes:
            # Map quote to Ompfinex's currency ID
            if quote == Quote.RLS:
                quote_id = "IRR"
                multiplier = 1  # API already returns in IRR (Toman)
            elif quote == Quote.USD:
                quote_id = "USDT"
                multiplier = 1
            else:
                continue  # Unsupported quote

            for base in bases:
                base_id = base.value  # e.g., "BTC", "USDT"
                market_id = market_map.get((quote_id, base_id))
                if market_id is not None:
                    tasks.append(fetch_orderbook(market_id, base, quote, multiplier))

        # 4. Run all tasks concurrently
        results = await asyncio.gather(*tasks)

        # 5. Aggregate successful results
        final_result = OrderBooks()
        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)

        return final_result