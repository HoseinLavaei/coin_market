import datetime
from decimal import Decimal
from typing import Optional

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin


class AbanTetherProvider:
    """Fetches OTC prices from AbanTether exchange. Supports IRT markets only."""
    provider_name: ProviderName = ProviderName.ABAN_TETHER

    @classmethod
    def _parse_coin(
            cls,
            quote: Quote,
            base: Base,
            data: dict,
    ) -> Optional[Coin]:
        """Parse a single market data entry into a Coin, or None if invalid."""
        try:
            buy_price = Decimal(str(data["buy_price"]))
            sell_price = Decimal(str(data["sell_price"]))
        except (KeyError, ValueError, TypeError):
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=buy_price,
            raw_sell_price=sell_price,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            buy_fee=Decimal(0.3) if base != Base.USDT else Decimal(0),
            sell_fee=Decimal(0.3) if base != Base.USDT else Decimal(0),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        raw = await get_json("https://api.abantether.com/api/v1/manager/otc/ticker")
        markets = raw.get("data", {}).get("markets", {})
        result = Coins()

        for quote in quotes:
            for base in bases:
                key = str(base.value) + ("IRT" if quote == Quote.TMN else str(quote.value))
                data = markets.get(key)
                if data is None:
                    continue
                coin = cls._parse_coin(quote, base, data)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, _quotes: list[Quote], _bases: list[Base]) -> OrderBooks:
        return OrderBooks()
