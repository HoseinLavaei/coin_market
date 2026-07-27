import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


def _optional(value):
    if value in ("-", "", None):
        return None
    return value


class WallexP2PProvider:
    provider_name = ProviderName.WALLEX_P2P
    """Wallex P2P API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://api.wallex.ir/v1/markets")

        symbols = json.get("result", {}).get("symbols", {})

        coins_data = []

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "TMN"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        for market in symbols.values():
            if market["quoteAsset"].upper() != quote_string:
                continue

            stats = market["stats"]

            if stats["lastPrice"] == "-":
                continue

            buy_price = stats.get("askPrice")
            sell_price = stats.get("bidPrice")

            if not _optional(buy_price) or not _optional(sell_price):
                continue

            coins_data.append({
                "base": market["baseAsset"].upper(),
                "buy_price": Decimal(str(buy_price).rstrip("0").rstrip(",")) * multiplier,
                "sell_price": Decimal(str(sell_price).rstrip("0").rstrip(",")) * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
            })

        return Coins.from_list(coins_data)


class WallexOTCProvider:
    provider_name = ProviderName.WALLEX_OTC
    """Wallex OTC API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # 1. Fetch available markets
        json = await get_json("https://api.wallex.ir/v1/otc/markets")
        symbols = json.get("result", {})

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "TMN"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        # Limit to core coins to avoid excessive API calls
        target_bases = {"BTC", "ETH", "USDT"}
        markets_to_fetch = []

        for symbol_name, market in symbols.items():
            if not symbol_name.endswith(quote_string):
                continue
            base = symbol_name.replace(quote_string, "").upper()
            if base in target_bases:
                markets_to_fetch.append({"symbol": symbol_name, "base": base})

        semaphore = asyncio.Semaphore(5)

        async def fetch_prices(market_info):
            async with semaphore:
                symbol = market_info["symbol"]
                base = market_info["base"]
                try:
                    # Fetch Buy and Sell prices concurrently
                    buy_task = get_json(f"https://api.wallex.ir/v1/otc/price", {"symbol": symbol, "side": "BUY"})
                    sell_task = get_json(f"https://api.wallex.ir/v1/otc/price", {"symbol": symbol, "side": "SELL"})
                    
                    buy_res, sell_res = await asyncio.gather(buy_task, sell_task)
                    
                    if not buy_res.get("success") or not sell_res.get("success"):
                        return None
                        
                    buy_price = Decimal(str(buy_res["result"]["price"])) * multiplier
                    sell_price = Decimal(str(sell_res["result"]["price"])) * multiplier
                    
                    return {
                        "base": base,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "quote": quote,
                        "provider": cls.provider_name,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    }
                except Exception:
                    return None

        tasks = [fetch_prices(m) for m in markets_to_fetch]
        results = await asyncio.gather(*tasks)
        coins_data = [r for r in results if r is not None]

        return Coins.from_list(coins_data)
