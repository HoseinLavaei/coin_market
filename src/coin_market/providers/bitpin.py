from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class BitpinProvider:
    provider_name = ProviderName.BITPIN
    """Bitpin API provider for cryptocurrency market data.

    Fetches market data for trading pairs. Bitpin does not provide market cap,
    circulating supply, or rank information.
    """

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        """Fetch coin data from the Bitpin API.

        Args:
            quote: Quote currency ("IRT" or "USDT").

        Returns:
            Coins collection with market data.
        """
        json = await get_json("https://api.bitpin.ir/v1/mkt/markets/")

        markets = json.get("results", [])

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "IRT"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        coins_data = [
            {
                "base": market["currency1"]["code"].upper(),
                "current_price": Decimal(market["price"]) * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
            }
            for market in markets
            if market["currency2"]["code"].upper() == quote_string
        ]

        return Coins.from_list(coins_data)
