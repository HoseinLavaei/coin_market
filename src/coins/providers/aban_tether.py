import datetime
from decimal import Decimal

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin


class AbanTetherProvider:
    """Fetches OTC prices from AbanTether exchange. Supports IRT markets only."""
    provider_name = ProviderName.ABAN_TETHER

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        json = await get_json("https://api.abantether.com/api/v1/manager/otc/ticker")
        markets = json["data"]["markets"]
        result = Coins()

        for quote in quotes:
            for base in bases:
                key = str(base.value) + ("IRT" if quote == Quote.TMN else str(quote.value))
                data = markets[key]

                coin = Coin(
                    provider=cls.provider_name,
                    base=base,
                    quote=quote,
                    raw_buy_price=Decimal(str(data["buy_price"])),
                    raw_sell_price=Decimal(str(data["sell_price"])),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    buy_fee=Decimal(0.3) if base != Base.USDT else Decimal(0),
                    sell_fee=Decimal(0.3) if base != Base.USDT else Decimal(0),
                )
                result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, _quotes: list[Quote], _bases: list[Base]) -> OrderBooks:
        return OrderBooks()
