from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


def optional(value):
    if value in (None, "", "-"):
        return None
    return value


class RamzinexProvider:
    """Ramzinex API provider."""

    @staticmethod
    def fetch(quote: Quote) -> Coins:
        json = get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")

        if json.get("status") != 0:
            raise RuntimeError("Ramzinex returned an invalid response.")

        coins_data = []

        currency_string = ""
        match quote:
            case Quote.RLS:
                currency_string = "irr"
            case Quote.USD:
                currency_string = "usdt"
            case _:
                raise ValueError(f"Unsupported currency: {quote}")

        for market in json["data"]:
            if market["quote_currency_symbol"]["en"] != currency_string:
                continue

            # Skip inactive markets
            current_price = market.get("sell")
            if current_price in (None, "", "-"):
                continue

            symbol = market["base_currency_symbol"]["en"].upper()

            coins_data.append({
                "base": symbol,
                "current_price": current_price,
                "quote": quote,
                "provider": ProviderName.RAMZINEX,
            })

        return Coins.from_list(coins_data)
