from ..coin import Coins
from .provider_base import Provider

class BitpinProvider(Provider):
    """Bitpin API provider for cryptocurrency market data.

    Fetches market data for trading pairs. Bitpin does not provide market cap,
    circulating supply, or rank information.
    """

    NAME = "Bitpin"
    URL = "https://api.bitpin.ir/v1/mkt/markets/"
    SUPPORTED_CURRENCIES = {"IRT", "USDT"}

    def get_params(self, currency:str) -> dict[str, str] | None:
        return None

    def _fetch(self, currency: str, json: dict) -> Coins:
        """Fetch coin data from the Bitpin API.

        Args:
            currency: Quote currency ("IRT" or "USDT").
            json: Parsed JSON response from the Bitpin API.

        Returns:
            Coins collection with market data.
        """

        markets = json.get("results", [])

        coins_data = [
            {
                "name": market["currency1"]["title"],
                "symbol": market["currency1"]["code"].upper(),
                "current_price": market["price"],
                "price_change_24h": market["price_info"]["change"],
                "high_24h": market["price_info"]["max"],
                "low_24h": market["price_info"]["min"],
                "market_cap": None,
                "volume_24h": market["price_info"]["value"],
                "circulating_supply": None,
                "rank": None,
                "currency": currency,
                "provider": self.NAME,
            }
            for market in markets
            if market["currency2"]["code"].upper() == currency
        ]

        return Coins.from_list(coins_data)