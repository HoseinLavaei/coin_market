from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


def optional(value):
    if value in (None, "", "-"):
        return None
    return value


class ExirProvider:
    """Exir exchange API provider."""

    @staticmethod
    def fetch(quote: Quote) -> Coins:
        coins_data = []
        json = get_json("https://api.exir.io/v2/tickers")
        for pair, ticker in json.items():
            if "-" not in pair:
                continue

            base, received_quote = pair.split("-", 1)

            currency_string = ""
            match quote:
                case Quote.RLS:
                    currency_string = "IRT"
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
                "current_price": last,
                "quote": quote,
                "provider": ProviderName.EXIR,
            })

        return Coins.from_list(coins_data)
