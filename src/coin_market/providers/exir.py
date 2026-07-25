from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


def optional(value):
    if value in (None, "", "-"):
        return None
    return value


class ExirProvider:
    provider_name = ProviderName.EXIR
    """Exir exchange API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        coins_data = []
        json = await get_json("https://api.exir.io/v2/tickers")
        for pair, ticker in json.items():
            pair = pair.upper()
            if "-" not in pair:
                continue

            base, received_quote = pair.split("-", 1)

            currency_string = ""
            multiplier = 1
            match quote:
                case Quote.RLS:
                    currency_string = "IRT"
                    multiplier = 10
                case Quote.USD:
                    currency_string = "USDT"
                case _:
                    raise ValueError(f"Unsupported currency: {quote}")

            if received_quote != currency_string:
                continue

            last = optional(ticker.get("last"))
            if last is None:
                continue

            coins_data.append({
                "base": base,
                "current_price": Decimal(last) * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
            })

        return Coins.from_list(coins_data)
