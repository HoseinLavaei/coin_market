from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


def get_params(quote: Quote) -> dict[str, str]:
    currency_string = ""
    match quote:
        case Quote.RLS:
            currency_string = "rls"
        case Quote.USD:
            currency_string = "usdt"
        case _:
            raise ValueError(f"Unsupported currency: {quote}")
    return {
        "srcCurrency": ",".join(("btc", "eth", "ltc", "usdt", "bnb", "xrp",)),
        "dstCurrency": currency_string,
    }


class NobitexProvider:
    provider_name = ProviderName.NOBITEX
    """Nobitex exchange API provider for Iranian cryptocurrency market.

    Supports Iranian Rial (RLS) as quote currency.
    """

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        json = await get_json("https://apiv2.nobitex.ir/market/stats", get_params(quote))
        if json.get("status") != "ok":
            raise RuntimeError("Nobitex returned an invalid response.")

        stats = json.get("stats", {})
        coins_data = []

        for market_key, market_data in stats.items():
            symbol = market_key.split("-")[0].upper()

            price = Decimal(market_data["latest"])

            coins_data.append({
                "base": symbol,
                "current_price": price,
                "quote": quote,
                "provider": cls.provider_name,
            })

        return Coins.from_list(coins_data)
