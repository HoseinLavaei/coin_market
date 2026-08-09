import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Quote, Coin, Base, OrderBook, Coins, OrderBooks, Order
from ..provider_name import ProviderName


class NobitexProvider:
    provider_name = ProviderName.NOBITEX

    @classmethod
    def _parse_market_data(cls, market_key: str, market_data: dict, bases: list[Base], quote: Quote) -> Coin | None:
        base_str = market_key.split("-")[0].upper()
        try:
            base = Base(base_str)
        except ValueError:
            return None

        if base not in bases:
            return None

        try:
            buy_price = Decimal(str(market_data["bestBuy"])) / 10
            sell_price = Decimal(str(market_data["bestSell"])) / 10
        except (KeyError, ValueError):
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            _buy_price=buy_price,
            _sell_price=sell_price,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            quote=quote,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        result = Coins()
        for quote in quotes:
            currency_string = "rls" if quote == Quote.TMN else "usdt"
            params = {
                "srcCurrency": ",".join(str(b.value).lower() for b in bases),
                "dstCurrency": currency_string,
            }
            try:
                json_data = await get_json("https://apiv2.nobitex.ir/market/stats", params)
            except (OSError, ValueError, TimeoutError):
                continue

            if json_data.get("status") != "ok":
                continue

            stats = json_data.get("stats", {})
            for market_key, market_data in stats.items():
                coin = cls._parse_market_data(market_key, market_data, bases, quote)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(quote: Quote, base: Base):
            quote_str = "IRT" if quote == Quote.TMN else "USDT"
            pair = f"{base.value}{quote_str}"
            async with semaphore:
                try:
                    url = f"https://apiv2.nobitex.ir/v3/orderbook/{pair}"
                    data = await get_json(url)
                    if data.get("status") != "ok":
                        return None

                    bids_raw = data.get("bids", [])
                    asks_raw = data.get("asks", [])
                    now = datetime.datetime.now(datetime.timezone.utc)

                    bids_list = [
                        Order(
                            coin=Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                _buy_price=Decimal(str(price)) / 10,
                                _sell_price=Decimal(str(price)) / 10,
                                buy_fee=Decimal(0.25),
                                sell_fee=Decimal(0.25),
                                timestamp=now,
                            ),
                            quantity=Decimal(str(amount)),
                        )
                        for price, amount in bids_raw
                    ]

                    asks_list = [
                        Order(
                            coin=Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                _buy_price=Decimal(str(price)) / 10,
                                _sell_price=Decimal(str(price)) / 10,
                                buy_fee=Decimal(0.25),
                                sell_fee=Decimal(0.25),
                                timestamp=now,
                            ),
                            quantity=Decimal(str(amount)),
                        )
                        for price, amount in asks_raw
                    ]

                    return (quote, base), OrderBook(asks=asks_list, bids=bids_list)

                except Exception as e:
                    print(f"Cant get nobitex's Orderbook:{e}")
                    return None

        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)
        return result
