from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class AbanTetherProvider:
    provider_name = ProviderName.ABAN_TETHER
    """AbanTether exchange API provider.

    Supports Iranian Rial (IRT) markets.
    """

    @classmethod
    async def fetch(cls, quote: Quote = Quote.RLS) -> Coins:
        json = await get_json("https://api.abantether.com/api/v1/manager/otc/ticker")
        markets = json["data"]["markets"]
        coins_data = []
        
        # AbanTether API returns prices in Toman (IRT).
        multiplier = 1
        match quote:
            case Quote.RLS:
                multiplier = 10
            case _:
                # Handle other quotes if supported by API, but currently it's IRT based.
                # For ,now we only support RLS derived from their IRC prices.
                pass

        for market in markets.values():
            if not market["active"]:
                continue
            coins_data.append({
                "provider": cls.provider_name,
                "quote": quote,
                "base": market["symbol"],
                # AbanTether exposes buy/sell prices.
                # We use the buy price as the current market price.
                "current_price": Decimal(market["buy_price"]) * multiplier,
            })
        return Coins.from_list(coins_data)
