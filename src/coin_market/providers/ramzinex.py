import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class RamzinexProvider:
    """Ramzinex exchange API provider."""
    provider_name = ProviderName.RAMZINEX

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """
        Fetch OTC (over‑the‑counter) prices from Ramzinex.
        Uses the public /exchange/api/v1.0/exchange/pairs endpoint.
        """
        try:
            json_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
            if json_data.get("status") != 0:
                return Coins()

            result = Coins()

            for quote in quotes:
                currency_string = "irr" if quote == Quote.RLS else "usdt"
                multiplier = 10 if quote == Quote.RLS else 1

                for market in json_data["data"]:
                    if market["quote_currency_symbol"]["en"] != currency_string:
                        continue

                    buy_price = market.get("buy")
                    sell_price = market.get("sell")

                    if buy_price in (None, "", "-") or sell_price in (None, "", "-"):
                        continue

                    base_str = market["base_currency_symbol"]["en"].upper()
                    try:
                        base = Base(base_str)
                    except ValueError:
                        continue

                    if base not in bases:
                        continue

                    coin = Coin(
                        provider=cls.provider_name,
                        base=base,
                        buy_price=Decimal(str(buy_price)) * multiplier,
                        sell_price=Decimal(str(sell_price)) * multiplier,
                        quote=quote,
                        timestamp=datetime.datetime.now(datetime.timezone.utc),
                    )
                    result.upsert(coin)

            return result

        except Exception:
            return Coins()

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        Fetch spot order books from Ramzinex.
        Uses separate endpoints for bids (buys) and asks (sells).
        """
        # 1. Fetch all available pairs
        json_pairs = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        if json_pairs.get("status") != 0:
            return OrderBooks()

        # 2. Pre‑index markets by (quote_symbol, base_symbol) -> pair_id
        market_map = {}
        for market in json_pairs.get("data", []):
            quote_sym = market["quote_currency_symbol"]["en"].lower()
            base_sym = market["base_currency_symbol"]["en"].upper()
            market_map[(quote_sym, base_sym)] = market["pair_id"]

        semaphore = asyncio.Semaphore(5)

        def clean_number(raw):
            """Remove commas and convert to Decimal safely."""
            if isinstance(raw, (int, float)):
                return Decimal(raw)
            if isinstance(raw, str):
                cleaned = raw.replace(",", "").strip()
                return Decimal(cleaned)
            raise ValueError(f"Unsupported type: {type(raw)}")

        async def fetch_orderbook(pair_id, base: Base, quote: Quote, multiplier):
            async with semaphore:
                try:
                    buys_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pair_id}/buys"
                    sells_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pair_id}/sells"

                    buys_data, sells_data = await asyncio.gather(
                        get_json(buys_url),
                        get_json(sells_url)
                    )

                    # Debug: uncomment to see raw responses
                    # print("Buys response:", buys_data)
                    # print("Sells response:", sells_data)

                    if buys_data.get("status") != 0 or sells_data.get("status") != 0:
                        return None

                    # Ramzinex returns "data" as a list of [price, amount]
                    bids_raw = buys_data.get("data", [])
                    asks_raw = sells_data.get("data", [])

                    # Ensure they are lists of lists with two elements
                    if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
                        return None

                    now = datetime.datetime.now(datetime.timezone.utc)

                    # ---- Build BIDS list ----
                    bids_list = []
                    for entry in bids_raw:
                        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                            continue
                        try:
                            price = clean_number(entry[0]) * multiplier
                            amount = clean_number(entry[1])
                        except (ValueError, TypeError):
                            continue
                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            quote=quote,
                            buy_price=price,
                            sell_price=price,
                            timestamp=now,
                        )
                        bids_list.append(Order(coin=coin, quantity=amount))

                    # ---- Build ASKS list ----
                    asks_list = []
                    for entry in asks_raw:
                        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                            continue
                        try:
                            price = clean_number(entry[0]) * multiplier
                            amount = clean_number(entry[1])
                        except (ValueError, TypeError):
                            continue
                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            quote=quote,
                            buy_price=price,
                            sell_price=price,
                            timestamp=now,
                        )
                        asks_list.append(Order(coin=coin, quantity=amount))

                    # If both sides are empty, return None (no useful data)
                    if not bids_list and not asks_list:
                        return None

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(f"Can't get Ramzinex's Orderbook:{e}")
                    # Log the error for debugging
                    # logger.error(f"Failed to fetch orderbook for pair_id {pair_id}: {e}")
                    return None

        # 3. Build tasks
        tasks = []
        for quote in quotes:
            if quote == Quote.RLS:
                quote_symbol = "irr"
                multiplier = 10
            elif quote == Quote.USD:
                quote_symbol = "usdt"
                multiplier = 1
            else:
                continue

            for base in bases:
                pair_id = market_map.get((quote_symbol, base.value.upper()))
                if pair_id is not None:
                    tasks.append(fetch_orderbook(pair_id, base, quote, multiplier))

        results = await asyncio.gather(*tasks)

        final_result = OrderBooks()
        for r in results:
            if r is not None:
                _, orderbook = r
                final_result.upsert(orderbook)

        return final_result