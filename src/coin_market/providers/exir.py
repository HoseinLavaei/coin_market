import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class ExirP2PProvider:
    provider_name = ProviderName.EXIR_P2P
    """Exir exchange P2P API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # Use orderbook endpoint for P2P for better accuracy (buy=lowest ask, sell=highest bid)
        # We need to fetch each pair's orderbook separately
        
        pairs_to_fetch = []
        if quote == Quote.RLS:
            pairs_to_fetch = ["btc-irt", "eth-irt", "usdt-irt"]
        elif quote == Quote.USD:
            pairs_to_fetch = ["btc-usdt", "eth-usdt"]

        multiplier = 10 if quote == Quote.RLS else 1
        semaphore = asyncio.Semaphore(2)

        async def fetch_pair(pair_name: str):
            async with semaphore:
                try:
                    json_data = await get_json(f"https://api.exir.io/v2/orderbook", {"symbol": pair_name})
                    data = json_data.get(pair_name)
                    if not data or not isinstance(data, dict):
                        return None
                    
                    bids = data.get("bids", [])
                    asks = data.get("asks", [])
                    
                    if not bids or not asks:
                        return None
                    
                    # Highest bid (sell price)
                    sell_price = Decimal(str(bids[0][0])) * multiplier
                    # Lowest ask (buy price)
                    buy_price = Decimal(str(asks[0][0])) * multiplier
                    
                    base = pair_name.split("-")[0].upper()
                    
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

        # Reorder to fetch USDT first as it is the primary focus for the bot
        sorted_pairs = sorted(pairs_to_fetch, key=lambda x: "usdt" not in x.lower())
        results = await asyncio.gather(*[fetch_pair(pair) for pair in sorted_pairs])
        coins_data = [r for r in results if r is not None]

        return Coins.from_list(coins_data)
