from .provider_base import get_json
from ..coin import Coins, Currency, ProviderName


def optional(value):
    if value in (None, "", "-"):
        return None
    return value


class ExirProvider:
    """Exir exchange API provider."""

    @staticmethod
    def fetch(currency: Currency) -> Coins:
        coins_data = []
        json = get_json("https://api.exir.io/v2/tickers")
        for pair, ticker in json.items():
            if "-" not in pair:
                continue

            base, quote = pair.split("-", 1)

            currency_string = ""
            match currency:
                case Currency.RLS:
                    currency_string = "IRT"
                case Currency.USD:
                    currency_string = "USDT"
                case _:
                    raise ValueError(f"Unsupported currency: {currency}")

            if quote != currency_string:
                continue

            last = optional(ticker.get("last"))
            if last is None:
                continue

            coins_data.append({
                "symbol": base,
                "current_price": last,
                "currency": currency,
                "provider": ProviderName.EXIR,
            })

        return Coins.from_list(coins_data)
