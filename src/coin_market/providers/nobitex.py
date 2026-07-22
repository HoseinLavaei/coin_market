from .provider_base import get_json
from ..coin import Coins, Quote, ProviderName


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
    """Nobitex exchange API provider for Iranian cryptocurrency market.

    Supports Iranian Rial (RLS) as quote currency.
    """

    @staticmethod
    def fetch(quote: Quote) -> Coins:
        json = get_json("https://apiv2.nobitex.ir/market/stats", get_params(quote))
        if json.get("status") != "ok":
            raise RuntimeError("Nobitex returned an invalid response.")

        stats = json.get("stats", {})
        coins_data = []

        for market_key, market_data in stats.items():
            symbol = market_key.split("-")[0].upper()

            coins_data.append({
                "base": symbol,
                "current_price": market_data["latest"],
                "quote": quote,
                "provider": ProviderName.NOBITEX,
            })

        return Coins.from_list(coins_data)
