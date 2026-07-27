import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class AbanTetherOTCProvider:
    provider_name = ProviderName.ABAN_TETHER_OTC
    """AbanTether exchange OTC API provider.

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
                "buy_price": Decimal(str(market["buy_price"])) * multiplier,
                "sell_price": Decimal(str(market["sell_price"])) * multiplier,
                "timestamp" : datetime.datetime.now(datetime.timezone.utc),
            })
        return Coins.from_list(coins_data)