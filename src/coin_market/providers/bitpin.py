import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks
from ..provider_name import ProviderName


class BitpinProvider:
    provider_name = ProviderName.BITPIN
    """Bitpin P2P/Market API provider."""

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        json = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = json.get("results", [])

        result: Coins = Coins()
        for quote in quotes:
            quote_string = ""
            multiplier = 1
            match quote:
                case Quote.RLS:
                    quote_string = "IRT"
                    multiplier = 10
                case Quote.USD:
                    quote_string = "USDT"
                case _:
                    continue

            for base in bases:
                for market in markets:
                    if market["currency2"]["code"].upper() == quote_string and market["currency1"]["code"].upper() == str(base.value):
                        price = Decimal(str(market["price"]))
                        buy_percent = Decimal(str(market.get("otc_buy_percent", "0")))
                        sell_percent = Decimal(str(market.get("otc_sell_percent", "0")))

                        buy_price = price * (Decimal("1") + buy_percent)
                        sell_price = price * (Decimal("1") - sell_percent)

                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            buy_price=buy_price * multiplier,
                            sell_price=sell_price * multiplier,
                            quote=quote,
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                        )
                        result.upsert(coin)
        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        # 1. Fetch all available markets
        data = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = data.get("results", [])

        # 2. Build a lookup map: (quote_code, base_code) -> market_id
        market_map = {}
        for market in markets:
            quote_code = market["currency2"]["code"].upper()
            base_code = market["currency1"]["code"].upper()
            market_map[(quote_code, base_code)] = market["id"]

        # 3. Prepare tasks based on the requested quotes and bases
        semaphore = asyncio.Semaphore(10)
        tasks = []

        for quote in quotes:
            # Map Quote enum to Bitpin's currency code and multiplier
            if quote == Quote.RLS:
                quote_string = "IRT"
                multiplier = 10
            elif quote == Quote.USD:
                quote_string = "USDT"
                multiplier = 1
            else:
                continue  # Skip unsupported quotes

            for base in bases:
                market_id = market_map.get((quote_string, base.value))
                if market_id is not None:
                    tasks.append(
                        fetch_orderbook(
                            market_id,
                            base,
                            quote,
                            multiplier,
                            semaphore,
                            cls.provider_name,
                        )
                    )

        # 4. Run all tasks concurrently
        results = await asyncio.gather(*tasks)

        # 5. Aggregate results into OrderBooks
        final_result = OrderBooks()
        for result in results:
            if result is not None:
                _, orderbook = result
                final_result.upsert(orderbook)

        return final_result

async def fetch_orderbook(market_id, base, quote, multiplier, semaphore, provider_name):
    async with semaphore:
        try:
            url = f"https://api.bitpin.ir/v4/mth/orderbook/{market_id}/"
            ob_json = await get_json(url)

            bids_raw = ob_json.get("bids", [])  # [[price, amount], ...]
            asks_raw = ob_json.get("asks", [])  # [[price, amount], ...]

            now = datetime.datetime.now(datetime.timezone.utc)

            # Build asks: each coin has both prices set to the ask price
            asks_list = [
                (
                    Coin(
                        provider=provider_name,
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

            # Build bids: each coin has both prices set to the bid price
            bids_list = [
                (
                    Coin(
                        provider=provider_name,
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

            return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

        except Exception:
            # Log the error here if you have logging set up
            return None