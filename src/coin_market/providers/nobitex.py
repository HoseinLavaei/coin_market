from .provider_base import Provider
from ..coin import Coins

class NobitexProvider(Provider):
    """Nobitex exchange API provider for Iranian cryptocurrency market.

    Supports Iranian Rial (RLS) as quote currency.
    """
    NAME = "Nobitex"
    URL = "https://apiv2.nobitex.ir/market/stats"
    SUPPORTED_CURRENCIES = {"RLS","USDT",}
    SUPPORTED_SYMBOLS = (
        "btc",
        "eth",
        "ltc",
        "usdt",
        "bnb",
        "xrp",
    )

    def get_params(self, currency: str) -> dict[str, str]:
        return {
            "srcCurrency": ",".join(self.SUPPORTED_SYMBOLS),
            "dstCurrency": currency.lower(),
        }

    def _fetch(self, currency: str, json: dict) -> Coins:
        if json.get("status") != "ok":
            raise RuntimeError("Nobitex returned an invalid response.")

        stats = json.get("stats", {})
        coins_data = []

        for market_key, market_data in stats.items():
            symbol = market_key.split("-")[0].upper()

            coins_data.append({
                "name": symbol,
                "symbol": symbol,
                "current_price": market_data["latest"],
                "price_change_24h": market_data["dayChange"],
                "high_24h": market_data["dayHigh"],
                "low_24h": market_data["dayLow"],
                "market_cap": None,
                "volume_24h": market_data["volumeDst"],
                "circulating_supply": None,
                "rank": None,
                "currency": currency,
                "provider": self.NAME,
            })

        return Coins.from_list(coins_data)