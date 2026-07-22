from .provider_base import get_json
from ..coin import Coins, Currency, ProviderName


class BitpinProvider:
    """Bitpin API provider for cryptocurrency market data.

    Fetches market data for trading pairs. Bitpin does not provide market cap,
    circulating supply, or rank information.
    """

    @staticmethod
    def fetch(currency: Currency) -> Coins:
        """Fetch coin data from the Bitpin API.

        Args:
            currency: Quote currency ("IRT" or "USDT").

        Returns:
            Coins collection with market data.
        """
        json = get_json("https://api.bitpin.ir/v1/mkt/markets/")

        markets = json.get("results", [])

        currency_string = ""
        match currency:
            case Currency.RLS:
                currency_string = "IRT"
            case Currency.USD:
                currency_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {currency}")

        coins_data = [
            {
                "symbol": market["currency1"]["code"].upper(),
                "current_price": market["price"],
                "currency": currency,
                "provider": ProviderName.BITPIN,
            }
            for market in markets
            if market["currency2"]["code"].upper() == currency_string
        ]

        return Coins.from_list(coins_data)
