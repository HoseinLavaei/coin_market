import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coin, Quote, Base, Coins, OrderBooks
from ..provider_name import ProviderName


class AbanTetherProvider:
    provider_name = ProviderName.ABAN_TETHER
    """AbanTether exchange OTC API provider.

    Supports Iranian Rial (IRT) markets.
    """

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        json = await get_json("https://api.abantether.com/api/v1/manager/otc/ticker")
        markets = json["data"]["markets"]
        pairs = [(quote, base) for quote in quotes for base in bases]
        result:Coins = Coins()
        for quote, base in pairs:
            match quote:
                case Quote.RLS:
                    multiplier = 10
                    data = markets[str(base.value) + "IRT"]
                case _:
                    multiplier = 1
                    data = markets[str(base.value) + str(quote.value)]
            coin = Coin(
                provider=cls.provider_name,
                quote=quote,
                base=base,
                buy_price=Decimal(str(data["buy_price"])) * multiplier,
                sell_price=Decimal(str(data["sell_price"])) * multiplier,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            result.upsert(coin)
        return result


    @classmethod
    async def get_orderbook(cls, _quotes: list[Quote] , _bases: list[Base]) -> OrderBooks:
        return OrderBooks()
