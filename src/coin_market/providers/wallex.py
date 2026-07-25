from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


def _optional(value):
    if value in ("-", "", None):
        return None
    return value

class WallexProvider:
    provider_name = ProviderName.WALLEX
    """Wallex API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://api.wallex.ir/v1/markets")

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

            current_price:str = stats["lastPrice"]
            current_price = current_price.rstrip("0")
            current_price = current_price.rstrip(",")

            coins_data.append({
                "base": market["baseAsset"].upper(),
                "current_price": Decimal(current_price) * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
            })

        return Coins.from_list(coins_data)
