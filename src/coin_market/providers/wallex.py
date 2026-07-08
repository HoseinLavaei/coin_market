from ..coin import Coins
from .provider_base import Provider

class WallexProvider(Provider):
    """Wallex API provider."""

    NAME = "Wallex"
    URL = "https://api.wallex.ir/v1/markets"
    SUPPORTED_CURRENCIES = {"TMN", "USDT"}

    def get_params(self, currency:str) -> dict[str, str] | None:
        return None

    def _fetch(self, currency: str, json: dict) -> Coins:
        def _optional(value):
            if value in ("-", "", None):
                return None
            return value

        symbols = json.get("result", {}).get("symbols", {})

        coins_data = []

        for market in symbols.values():
            if market["quoteAsset"].upper() != currency:
                continue

            stats = market["stats"]

            if stats["lastPrice"] == "-":
                continue

            coins_data.append({
                "name": market.get("enName", market["baseAsset"]),
                "symbol": market["baseAsset"].upper(),

                "current_price": stats["lastPrice"],
                "price_change_24h": _optional(stats.get("24h_ch")),
                "high_24h": _optional(stats.get("24h_highPrice")),
                "low_24h": _optional(stats.get("24h_lowPrice")),

                "market_cap": None,
                "volume_24h": _optional(stats.get("24h_quoteVolume")),
                "circulating_supply": None,
                "rank": None,

                "currency": currency,
                "provider": self.NAME,
            })

        return Coins.from_list(coins_data)