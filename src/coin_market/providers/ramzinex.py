from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


def optional(value):
    if value in (None, "", "-"):
        return None
    return value


class RamzinexProvider:
    provider_name = ProviderName.RAMZINEX
    """Ramzinex API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")

        if json.get("status") != 0:
            raise RuntimeError("Ramzinex returned an invalid response.")

        coins_data = []

        currency_string = ""
        multiplier = 1
        match quote:
            case Quote.RLS:
                currency_string = "irr"
                multiplier = 1
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
                "current_price": Decimal(current_price) * multiplier,
                "quote": quote,
                "provider": cls.provider_name,
            })

        return Coins.from_list(coins_data)
