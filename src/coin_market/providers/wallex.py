from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


def _optional(value):
    if value in ("-", "", None):
        return None
    return value


class WallexProvider:
    """Wallex API provider."""

    SUPPORTED_CURRENCIES = {"TMN", "USDT"}

    @staticmethod
    def fetch(quote: Quote) -> Coins:
        json = get_json("https://api.wallex.ir/v1/markets")

        symbols = json.get("result", {}).get("symbols", {})

        coins_data = []

        quote_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                quote_string = "TMN"
                multiplier = 10
            case Quote.USD:
                quote_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        for market in symbols.values():
            if market["quoteAsset"].upper() != quote_string:
                continue

            stats = market["stats"]

            if stats["lastPrice"] == "-":
                continue

            coins_data.append({
                "base": market["baseAsset"].upper(),
                "current_price": stats["lastPrice"] * multiplier,
                "quote": quote,
                "provider": ProviderName.WALLEX,
            })

        return Coins.from_list(coins_data)
