from .provider_base import Provider
from ..coin import Coins


class RamzinexProvider(Provider):
    """Ramzinex API provider."""

    NAME = "Ramzinex"
    URL = "https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs"
    SUPPORTED_CURRENCIES = {
        "irr",
        "usdt",
        "btc",
    }

    def get_params(self, currency: str) -> dict[str, str] | None:
        return None

    def _fetch(self, currency: str, json: dict) -> Coins:
        if json.get("status") != 0:
            raise RuntimeError("Ramzinex returned an invalid response.")

        def optional(value):
            if value in (None, "", "-"):
                return None
            return value

        coins_data = []

        for market in json["data"]:
            if market["quote_currency_symbol"]["en"] != currency:
                continue

            # Skip inactive markets
            current_price = market.get("sell")
            if current_price in (None, "", "-"):
                continue

            financial = market.get("financial", {}).get("last24h", {})

            symbol = market["base_currency_symbol"]["en"]

            coins_data.append({
                "name": symbol,
                "symbol": symbol,

                "current_price": current_price,

                "price_change_24h": optional(financial.get("change_percent")),
                "high_24h": optional(financial.get("highest")),
                "low_24h": optional(financial.get("lowest")),

                "market_cap": None,
                "volume_24h": optional(financial.get("quote_volume")),
                "circulating_supply": None,
                "rank": None,

                "currency": currency,
                "provider": self.NAME,
            })

        return Coins.from_list(coins_data)
