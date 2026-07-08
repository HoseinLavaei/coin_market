from decimal import Decimal

from ..coin import Coins
from .provider_base import Provider


class ExirProvider(Provider):
    """Exir exchange API provider."""

    NAME = "Exir"
    URL = "https://api.exir.io/v2/tickers"
    SUPPORTED_CURRENCIES = {
        "USDT",
        "IRT",
        "BTC",
        "ETH",
    }

    def get_params(self, currency: str) -> dict[str, str] | None:
        return None

    def _fetch(self, currency: str, json: dict) -> Coins:
        def optional(value):
            if value in (None, "", "-"):
                return None
            return value

        coins_data = []

        for pair, ticker in json.items():
            if "-" not in pair:
                continue

            base, quote = pair.split("-", 1)

            if quote != currency:
                continue

            last = optional(ticker.get("last"))
            if last is None:
                continue

            open_price = optional(ticker.get("open"))

            change = None
            if open_price is not None:
                open_decimal = Decimal(str(open_price))
                last_decimal = Decimal(str(last))

                if open_decimal != 0:
                    change = (
                        (last_decimal - open_decimal)
                        / open_decimal
                        * Decimal("100")
                    )

            coins_data.append({
                "name": base,
                "symbol": base,

                "current_price": last,

                "price_change_24h": change,
                "high_24h": optional(ticker.get("high")),
                "low_24h": optional(ticker.get("low")),

                "market_cap": None,
                "volume_24h": optional(ticker.get("volume")),
                "circulating_supply": None,
                "rank": None,

                "currency": currency,
                "provider": self.NAME,
            })

        return Coins.from_list(coins_data)