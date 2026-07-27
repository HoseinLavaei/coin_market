import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class RamzinexP2PProvider:
    provider_name = ProviderName.RAMZINEX_P2P
    """Ramzinex P2P API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # 1. Fetch pairs to get pair_ids
        json_pairs = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        if json_pairs.get("status") != 0:
            return Coins()

        currency_string = "irr" if quote == Quote.RLS else "usdt"
        multiplier = 10 if quote == Quote.RLS else 1

        # We only care about main coins for P2P orderbook fetching to avoid too many requests
        target_symbols = {"BTC", "ETH", "USDT"}
        markets_to_fetch = []

        for market in json_pairs["data"]:
            if market["quote_currency_symbol"]["en"] != currency_string:
                continue
            symbol = market["base_currency_symbol"]["en"].upper()
            if symbol in target_symbols:
                markets_to_fetch.append({
                    "id": market["pair_id"],
                    "symbol": symbol
                })

        semaphore = asyncio.Semaphore(5)

        async def fetch_orderbook(market_info):
            async with semaphore:
                pair_id = market_info["id"]
                symbol = market_info["symbol"]
                try:
                    # Fetch buys (bids) and sells (asks)
                    # Ramzinex API: /orderbooks/{pair_id}/buys and /orderbooks/{pair_id}/sells
                    buys_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pair_id}/buys"
                    sells_url = f"https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/{pair_id}/sells"
                    
                    buys_task = get_json(buys_url)
                    sells_task = get_json(sells_url)
                    
                    buys_data, sells_data = await asyncio.gather(buys_task, sells_task)
                    
                    if buys_data.get("status") != 0 or sells_data.get("status") != 0:
                        return None
                    
                    bids = buys_data.get("data", [])
                    asks = sells_data.get("data", [])
                    
                    if not bids or not asks:
                        return None
                    
                    # buys (bids) are descending. Highest bid is first.
                    sell_price = Decimal(str(bids[0][0])) * multiplier
                    # sells (asks) are descending. Lowest ask is last.
                    buy_price = Decimal(str(asks[-1][0])) * multiplier
                    
                    return {
                        "base": symbol,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "quote": quote,
                        "provider": cls.provider_name,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    }
                except Exception:
                    return None

        tasks = [fetch_orderbook(m) for m in markets_to_fetch]
        results = await asyncio.gather(*tasks)
        coins_data = [r for r in results if r is not None]

        return Coins.from_list(coins_data)


class RamzinexOTCProvider:
    provider_name = ProviderName.RAMZINEX_OTC
    """Ramzinex OTC API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # Use the pairs endpoint for OTC prices as it provides immediate buy/sell prices
        try:
            json_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
            if json_data.get("status") != 0:
                return Coins()

            currency_string = "irr" if quote == Quote.RLS else "usdt"
            # Pairs API returns prices in IRR for irr quote, we need RLS
            multiplier = 10 if quote == Quote.RLS else 1
            
            coins_data = []
            for market in json_data["data"]:
                if market["quote_currency_symbol"]["en"] != currency_string:
                    continue

                buy_price = market.get("buy")
                sell_price = market.get("sell")
                
                if buy_price in (None, "", "-") or sell_price in (None, "", "-"):
                    continue

                symbol = market["base_currency_symbol"]["en"].upper()
                coins_data.append({
                    "base": symbol,
                    "buy_price": Decimal(str(buy_price)) * multiplier,
                    "sell_price": Decimal(str(sell_price)) * multiplier,
                    "quote": quote,
                    "provider": cls.provider_name,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                })
            return Coins.from_list(coins_data)
        except Exception:
            return Coins()
