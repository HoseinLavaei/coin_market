import asyncio
import datetime
from decimal import Decimal

from .provider_base import get_json
from ..coin import Coins, Quote
from ..provider_name import ProviderName


class NobitexP2PProvider:
    provider_name = ProviderName.NOBITEX_P2P
    """Nobitex P2P API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # Use orderbook API for P2P accuracy
        pairs = []
        if quote == Quote.RLS:
            pairs = ["BTCIRT", "ETHIRT", "USDTIRT"]
        elif quote == Quote.USD:
            pairs = ["BTCUSDT", "ETHUSDT"]

        semaphore = asyncio.Semaphore(5)

        async def fetch_pair(pair: str):
            async with semaphore:
                try:
                    url = f"https://apiv2.nobitex.ir/v3/orderbook/{pair}"
                    data = await get_json(url)
                    if data.get("status") != "ok":
                        return None

                    bids = data.get("bids", [])
                    asks = data.get("asks", [])

                    if not bids or not asks:
                        return None

                    # Sell price is highest bid
                    sell_price = Decimal(str(bids[0][0]))
                    # Buy price is lowest ask
                    buy_price = Decimal(str(asks[0][0]))

                    # Extract base currency from pair name
                    # Nobitex pairs are usually like BTCIRT or BTCUSDT
                    if pair.endswith("IRT"):
                        base = pair[:-3]
                    elif pair.endswith("USDT"):
                        base = pair[:-4]
                    else:
                        base = pair

                    return {
                        "base": base,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "quote": quote,
                        "provider": cls.provider_name,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    }
                except Exception:
                    return None

        tasks = [fetch_pair(p) for p in pairs]
        results = await asyncio.gather(*tasks)
        coins_data = [r for r in results if r is not None]

        return Coins.from_list(coins_data)


class NobitexOTCProvider:
    provider_name = ProviderName.NOBITEX_OTC
    """Nobitex OTC (Fast Trade) API provider."""

    @classmethod
    async def fetch(cls, quote: Quote) -> Coins:
        # For OTC, we can use the stats endpoint as a proxy for fast trade prices
        # as Nobitex doesn't expose a separate public OTC API clearly.
        currency_string = "rls" if quote == Quote.RLS else "usdt"
        params = {
            "srcCurrency": ",".join(("btc", "eth", "usdt")),
            "dstCurrency": currency_string,
        }
        
        try:
            json_data = await get_json("https://apiv2.nobitex.ir/market/stats", params)
            if json_data.get("status") != "ok":
                return Coins()

            stats = json_data.get("stats", {})
            coins_data = []

            for market_key, market_data in stats.items():
                symbol = market_key.split("-")[0].upper()

                # For OTC/Fast Trade proxy, we use best buy/sell from ticker
                buy_price = Decimal(str(market_data["bestBuy"]))
                sell_price = Decimal(str(market_data["bestSell"]))

                coins_data.append({
                    "base": symbol,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "quote": quote,
                    "provider": cls.provider_name,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                })
            return Coins.from_list(coins_data)
        except Exception:
            return Coins()
