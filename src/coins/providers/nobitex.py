import asyncio
import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, Order, OrderBook


class NobitexProvider:
    """Fetches OTC and order book data from Nobitex exchange."""
    provider_name: ProviderName = ProviderName.NOBITEX

    @classmethod
    def _parse_market_data(
            cls,
            market_key: str,
            market_data: dict[str, Any],
            bases: list[Base],
            quote: Quote,
    ) -> Optional[Coin]:
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
            quote=quote,
            raw_buy_price=buy_price,
            raw_sell_price=sell_price,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
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
                data = await get_json("https://apiv2.nobitex.ir/market/stats", params)
            except (OSError, ValueError, TimeoutError):
                continue

            if data.get("status") != "ok":
                continue

            for market_key, market_data in data.get("stats", {}).items():
                coin = cls._parse_market_data(market_key, market_data, bases, quote)
                if coin:
                    result.upsert(coin)

        return result

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        result = OrderBooks()
        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(
                quote: Quote,
                base: Base,
        ) -> Optional[tuple[tuple[Quote, Base], OrderBook]]:
            quote_str = "IRT" if quote == Quote.TMN else "USDT"
            pair = f"{base.value}{quote_str}"

            async with semaphore:
                data = await get_json(f"https://apiv2.nobitex.ir/v2/depth/{pair}")
                if data.get("status") != "ok":
                    return None

                bids_raw: list[list[Any]] = data.get("bids", [])
                asks_raw: list[list[Any]] = data.get("asks", [])
                now = datetime.datetime.now(datetime.timezone.utc)

                def build_orders(raw: list[list[Any]]) -> list[Order]:
                    orders = []
                    for price, amount in raw:
                        try:
                            price_dec = Decimal(str(price)) / 10
                            amount_dec = Decimal(str(amount))
                        except (ValueError, TypeError):
                            continue
                        coin = Coin(
                            provider=cls.provider_name,
                            base=base,
                            quote=quote,
                            raw_buy_price=price_dec,
                            raw_sell_price=price_dec,
                            buy_fee=Decimal(0.25),
                            sell_fee=Decimal(0.25),
                            timestamp=now,
                        )
                        orders.append(Order(coin=coin, quantity=amount_dec))
                    return orders

                bids = build_orders(bids_raw)
                asks = build_orders(asks_raw)
                if not bids and not asks:
                    return None

                return (quote, base), OrderBook(asks=asks, bids=bids)

        tasks = [fetch_pair(quote, base) for quote in quotes for base in bases]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None:
                _, orderbook = r
                result.upsert(orderbook)

        return result
