import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class BitpinP2PProvider:
    provider_name = ProviderName.BITPIN_P2P
    """Bitpin P2P/Market API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = json.get("results", [])

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "IRT"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        semaphore = asyncio.Semaphore(10)

        async def fetch_orderbook(market_id, base):
            async with semaphore:
                try:
                    url = f"https://api.bitpin.ir/v4/mth/orderbook/{market_id}/?limit=1"
                    ob_json = await get_json(url)
                    
                    # Highest bid (sell price)
                    bids = ob_json.get("bids", [])
                    sell_price = Decimal(bids[0][0]) if bids else None
                    
                    # Lowest ask (buy price)
                    asks = ob_json.get("asks", [])
                    buy_price = Decimal(asks[0][0]) if asks else None
                    
                    if sell_price is None or buy_price is None:
                        return None

                    return {
                        "base": base,
                        "buy_price": buy_price * multiplier,
                        "sell_price": sell_price * multiplier,
                        "quote": quote,
                        "provider": cls.provider_name,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    }
                except Exception:
                    return None

        tasks = []
        for market in markets:
            if market["currency2"]["code"].upper() != quote_string:
                continue
            
            market_id = market["id"]
            base = market["currency1"]["code"].upper()
            tasks.append(fetch_orderbook(market_id, base))

        results = await asyncio.gather(*tasks)
        coins_data = [r for r in results if r is not None]

        return Coins.from_list(coins_data)

class BitpinOTCProvider:
    provider_name = ProviderName.BITPIN_OTC
    """Bitpin OTC API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = json.get("results", [])

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "IRT"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        coins_data = []
        for market in markets:
            if market["currency2"]["code"].upper() != quote_string:
                continue

            base = market["currency1"]["code"].upper()
            price = Decimal(str(market["price"]))

            buy_percent = Decimal(str(market.get("otc_buy_percent", "0")))
            sell_percent = Decimal(str(market.get("otc_sell_percent", "0")))

            buy_price = price * (Decimal("1") + buy_percent)
            sell_price = price * (Decimal("1") - sell_percent)

            coins_data.append({
                "base": base,
                "buy_price": buy_price * multiplier,
                "sell_price": sell_price * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
            })

        return Coins.from_list(coins_data)
