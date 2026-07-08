from .provider_base import Provider
from ..coin import Coins


class AbanTetherProvider(Provider):
    """AbanTether exchange API provider.

    Supports Iranian Rial (IRT) markets.
    """

    NAME = "AbanTether"
    URL = "https://api.abantether.com/api/v1/manager/otc/ticker"
    SUPPORTED_CURRENCIES = {"IRT"}

    def get_params(self, currency: str) -> dict[str, str] | None:
        return None

    def _fetch(self, currency: str, json: dict) -> Coins:
        markets = json["data"]["markets"]

        coins_data = []

        for market in markets.values():
            if not market["active"]:
                continue

            coins_data.append({
                "provider": self.NAME,
                "currency": "IRT",

                "name": market["symbol"],
                "symbol": market["symbol"],

                # AbanTether exposes buy/sell prices.
                # We use the buy price as the current market price.
                "current_price": market["buy_price"],

                # This endpoint does not expose 24h statistics.
                "price_change_24h": None,
                "high_24h": None,
                "low_24h": None,
                "volume_24h": None,

                "market_cap": None,
                "circulating_supply": None,
                "rank": None,
            })

        return Coins.from_list(coins_data)
