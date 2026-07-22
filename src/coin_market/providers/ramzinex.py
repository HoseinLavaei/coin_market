from .provider_base import get_json
from ..coin import Coins, Currency, ProviderName

def optional(value):
    if value in (None, "", "-"):
        return None
    return value

class RamzinexProvider:
    """Ramzinex API provider."""

    @staticmethod
    def fetch(currency: Currency) -> Coins:
        json = get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs", None)

        if json.get("status") != 0:
            raise RuntimeError("Ramzinex returned an invalid response.")

        coins_data = []

        currency_string = ""
        match currency:
            case Currency.RLS:
                currency_string = "irr"
            case Currency.USD:
                currency_string = "usdt"
            case _:
                raise ValueError(f"Unsupported currency: {currency}")

        for market in json["data"]:
            if market["quote_currency_symbol"]["en"] != currency_string:
                continue

            # Skip inactive markets
            current_price = market.get("sell")
            if current_price in (None, "", "-"):
                continue

            symbol = market["base_currency_symbol"]["en"].upper()

            coins_data.append({
                "symbol": symbol,
                "current_price": current_price,
                "currency": currency,
                "provider": ProviderName.RAMZINEX,
            })

        return Coins.from_list(coins_data)
