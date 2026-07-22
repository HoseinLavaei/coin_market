from .provider_base import get_json
from ..coin import Coins, Currency, ProviderName


def _optional(value):
    if value in ("-", "", None):
        return None
    return value

class WallexProvider:
    """Wallex API provider."""

    SUPPORTED_CURRENCIES = {"TMN", "USDT"}

    @staticmethod
    def fetch(currency: Currency) -> Coins:
        json = get_json("https://api.wallex.ir/v1/markets", None)

        symbols = json.get("result", {}).get("symbols", {})

        coins_data = []

        currency_string = ""
        multiplier = 1
        match currency:
            case Currency.RLS:
                currency_string = "TMN"
                multiplier = 10
            case Currency.USD:
                currency_string = "USDT"
            case _:
                raise ValueError(f"Unsupported currency: {currency}")

        for market in symbols.values():
            if market["quoteAsset"].upper() != currency_string:
                continue

            stats = market["stats"]

            if stats["lastPrice"] == "-":
                continue

            coins_data.append({
                "symbol": market["baseAsset"].upper(),
                "current_price": stats["lastPrice"]*multiplier,
                "currency": currency,
                "provider": ProviderName.WALLEX,
            })

        return Coins.from_list(coins_data)
