from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


class BitpinProvider:
    """Bitpin API provider for cryptocurrency market data.

    Fetches market data for trading pairs. Bitpin does not provide market cap,
    circulating supply, or rank information.
    """

    @staticmethod
    def fetch(quote: Quote) -> Coins:
        """Fetch coin data from the Bitpin API.

        Args:
            quote: Quote currency ("IRT" or "USDT").

        Returns:
            Coins collection with market data.
        """
        json = get_json("https://api.bitpin.ir/v1/mkt/markets/")

        markets = json.get("results", [])

        quote_string = ""
        match quote:
            case Quote.RLS:
                quote_string = "IRT"
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        coins_data = [
            {
                "base": market["currency1"]["code"].upper(),
                "current_price": market["price"],
                "quote": quote,
                "provider": ProviderName.BITPIN,
            }
            for market in markets
            if market["currency2"]["code"].upper() == quote_string
        ]

        return Coins.from_list(coins_data)
