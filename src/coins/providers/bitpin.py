import asyncio
import datetime
from decimal import Decimal

from .base import get_json
from .. import Coin, Quote, Base, Coins, OrderBooks, ProviderName, Order, OrderBook


class BitpinProvider:
    """Fetches OTC and order book data from Bitpin exchange."""
    provider_name = ProviderName.BITPIN

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        data = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = data.get("results", [])
        result = Coins()

        for quote in quotes:
            quote_string = cls._get_quote_string(quote)
            if quote_string is None:
                continue

            for base in bases:
                coin = cls._find_otc_market(markets, quote, base, quote_string)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    def _get_quote_string(cls, quote: Quote) -> str | None:
        if quote == Quote.TMN:
            return "IRT"
        if quote == Quote.USD:
            return "USDT"
        return None

    @classmethod
    def _find_otc_market(cls, markets: list, quote: Quote, base: Base, quote_string: str) -> Coin | None:
        for market in markets:
            if market["currency2"]["code"].upper() != quote_string:
                continue
            if market["currency1"]["code"].upper() != str(base.value):
                continue

            price = Decimal(str(market["price"]))
            buy_percent = Decimal(str(market.get("otc_buy_percent", "0")))
            sell_percent = Decimal(str(market.get("otc_sell_percent", "0")))

            return Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
                raw_buy_price=price * (Decimal("1") + buy_percent),
                raw_sell_price=price * (Decimal("1") - sell_percent),
                buy_fee=Decimal(0),
                sell_fee=Decimal(0),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
        return None

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        market_map = await cls._build_market_map()
        if not market_map:
            return OrderBooks()

        semaphore = asyncio.Semaphore(10)
        tasks = []

        for quote in quotes:
            quote_string = cls._get_quote_string(quote)
            if quote_string is None:
                continue

            for base in bases:
                market_id = market_map.get((quote_string, base.value))
                if market_id is not None:
                    tasks.append(
                        cls._fetch_orderbook(market_id, base, quote, semaphore)
                    )

        results = await asyncio.gather(*tasks)
        final_result = OrderBooks()

        for item in results:
            if item is not None:
                _, orderbook = item
                final_result.upsert(orderbook)

        return final_result

    @classmethod
    async def _build_market_map(cls) -> dict[tuple[str, str], int]:
        data = await get_json("https://api.bitpin.ir/v1/mkt/markets/")
        markets = data.get("results", [])

        market_map = {}
        for market in markets:
            quote_code = market["currency2"]["code"].upper()
            base_code = market["currency1"]["code"].upper()
            market_map[(quote_code, base_code)] = market["id"]

        return market_map

    @classmethod
    async def _fetch_orderbook(cls, market_id: int, base: Base, quote: Quote, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                url = f"https://api.bitpin.ir/v4/mth/orderbook/{market_id}/"
                data = await get_json(url)

                bids_raw = data.get("bids", [])
                asks_raw = data.get("asks", [])
                now = datetime.datetime.now(datetime.timezone.utc)

                def build_orders(raw) -> list[Order]:
                    return [
                        Order(
                            coin=Coin(
                                provider=cls.provider_name,
                                base=base,
                                quote=quote,
                                raw_buy_price=Decimal(str(price)),
                                raw_sell_price=Decimal(str(price)),
                                buy_fee=Decimal(0.35),
                                sell_fee=Decimal(0.35),
                                timestamp=now,
                            ),
                            quantity=Decimal(str(amount)),
                        )
                        for price, amount in raw
                    ]

                return (quote, base), OrderBook(
                    asks=build_orders(asks_raw),
                    bids=build_orders(bids_raw),
                )

            except Exception as exc:
                print(f"Bitpin orderbook fetch failed: {exc}")
                return None
