from .provider_base import get_json
from ..coin import Coins, Currency, ProviderName


def get_params(currency: Currency) -> dict[str, str]:
    currency_string = ""
    match currency:
        case Currency.RLS:
            currency_string = "rls"
        case Currency.USD:
            currency_string = "usdt"
        case _:
            raise ValueError(f"Unsupported currency: {currency}")
    return {
        "srcCurrency": ",".join(("btc","eth","ltc","usdt","bnb","xrp",)),
        "dstCurrency": currency_string,
    }

class NobitexProvider:
    """Nobitex exchange API provider for Iranian cryptocurrency market.

    Supports Iranian Rial (RLS) as quote currency.
    """

    @staticmethod
    def fetch(currency: Currency) -> Coins:
        json = get_json("https://apiv2.nobitex.ir/market/stats", get_params(currency))
        if json.get("status") != "ok":
            raise RuntimeError("Nobitex returned an invalid response.")

        stats = json.get("stats", {})
        coins_data = []

        for market_key, market_data in stats.items():
            symbol = market_key.split("-")[0].upper()

            coins_data.append({
                "symbol": symbol,
                "current_price": market_data["latest"],
                "currency": currency,
                "provider": ProviderName.NOBITEX,
            })

        return Coins.from_list(coins_data)
