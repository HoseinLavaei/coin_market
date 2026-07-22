from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


class AbanTetherProvider:
    """AbanTether exchange API provider.

    Supports Iranian Rial (IRT) markets.
    """

    @staticmethod
    def fetch(quote: Quote = Quote.RLS) -> Coins:
        json = get_json("https://api.abantether.com/api/v1/manager/otc/ticker")
        markets = json["data"]["markets"]
        coins_data = []
        for market in markets.values():
            if not market["active"]:
                continue
            coins_data.append({
                "provider": ProviderName.ABAN_TETHER,
                "quote": quote,
                "base": market["symbol"],
                # AbanTether exposes buy/sell prices.
                # We use the buy price as the current market price.
                "current_price": market["buy_price"],
            })
        return Coins.from_list(coins_data)
