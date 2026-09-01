import datetime
from decimal import Decimal
from typing import Optional, Any

from .base import get_json
from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins, Coin, OrderBook, Order


class RamzinexProvider:
    """Fetches OTC and order book data from Ramzinex exchange."""
    provider_name: ProviderName = ProviderName.RAMZINEX

    @staticmethod
    def _clean_number(raw_value: Any) -> Decimal:
        if isinstance(raw_value, (int, float)):
            return Decimal(raw_value)
        if isinstance(raw_value, str):
            return Decimal(raw_value.replace(",", "").strip())
        raise ValueError(f"Unsupported type: {type(raw_value)}")

    @classmethod
    def _get_quote_string(cls, quote: Quote) -> Optional[str]:
        if quote == Quote.TMN:
            return "irr"
        if quote == Quote.USD:
            return "usdt"
        return None

    # ─── Pair ID mapping ──────────────────────────────────────────

    @classmethod
    async def _fetch_pairs_map(
        cls,
    ) -> tuple[dict[tuple[str, str], int], dict[int, tuple[str, str]]]:
        """
        Fetch and return both:
        - forward map: (quote_sym, base_sym) -> pair_id
        - reverse map: pair_id -> (quote_sym, base_sym)
        """
        try:
            data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return {}, {}

        if data.get("status") != 0:
            return {}, {}

        forward: dict[tuple[str, str], int] = {}
        reverse: dict[int, tuple[str, str]] = {}
        for market in data.get("data", []):
            quote_sym = market["quote_currency_symbol"]["en"].lower()
            base_sym = market["base_currency_symbol"]["en"].upper()
            pair_id = market["pair_id"]
            forward[(quote_sym, base_sym)] = pair_id
            reverse[pair_id] = (quote_sym, base_sym)

        return forward, reverse

    # ─── OTC ──────────────────────────────────────────────────────

    @classmethod
    def _parse_otc_market(
        cls,
        market: dict[str, Any],
        quote: Quote,
        bases: list[Base],
    ) -> Optional[Coin]:
        buy_price = market.get("buy")
        sell_price = market.get("sell")

        if buy_price in (None, "", "-") or sell_price in (None, "", "-"):
            return None

        base_str = market["base_currency_symbol"]["en"].upper()
        try:
            base = Base(base_str)
        except ValueError:
            return None

        if base not in bases:
            return None

        return Coin(
            provider=cls.provider_name,
            base=base,
            quote=quote,
            raw_buy_price=Decimal(str(buy_price)) / 10,
            raw_sell_price=Decimal(str(sell_price)) / 10,
            buy_fee=Decimal(0),
            sell_fee=Decimal(0),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        """OTC: fetch full pairs list and parse all markets."""
        try:
            pairs_data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs")
        except (OSError, ValueError, TimeoutError):
            return Coins()

        if pairs_data.get("status") != 0:
            return Coins()

        result = Coins()

        for quote in quotes:
            currency_string = cls._get_quote_string(quote)
            if currency_string is None:
                continue

            for market in pairs_data.get("data", []):
                if market["quote_currency_symbol"]["en"] != currency_string:
                    continue

                coin = cls._parse_otc_market(market, quote, bases)
                if coin:
                    result.upsert(coin)

        return result

    # ─── Orderbook (P2P) ─────────────────────────────────────────

    @classmethod
    def _build_order_list(
        cls,
        entries: list[list[Any]],
        quote: Quote,
        base: Base,
        now: datetime.datetime,
    ) -> list[Order]:
        orders: list[Order] = []
        for entry in entries:
            if len(entry) < 2:
                continue
            try:
                price = cls._clean_number(entry[0]) / 10
                amount = cls._clean_number(entry[1])
            except (ValueError, TypeError):
                continue

            coin = Coin(
                provider=cls.provider_name,
                base=base,
                quote=quote,
                raw_buy_price=price,
                raw_sell_price=price,
                buy_fee=Decimal(0.25),
                sell_fee=Decimal(0.25),
                timestamp=now,
            )
            orders.append(Order(coin=coin, quantity=amount))

        return orders

    @classmethod
    def _get_needed_pair_ids(
        cls,
        quotes: list[Quote],
        bases: list[Base],
        forward_map: dict[tuple[str, str], int],
    ) -> set[int]:
        """Build a set of pair IDs needed for the given quotes and bases."""
        needed: set[int] = set()
        for quote in quotes:
            quote_symbol = cls._get_quote_string(quote)
            if quote_symbol is None:
                continue
            for base in bases:
                pair_id = forward_map.get((quote_symbol, base.value.upper()))
                if pair_id is not None:
                    needed.add(pair_id)
        return needed

    @classmethod
    def _process_orderbook_entry(
        cls,
        pair_id: int,
        order_data: dict[str, Any],
        reverse_map: dict[int, tuple[str, str]],
        quotes: list[Quote],
        bases: list[Base],
        now: datetime.datetime,
    ) -> Optional[OrderBook]:
        """Process a single orderbook entry from the batch response."""
        buys_raw = order_data.get("buys", [])
        sells_raw = order_data.get("sells", [])

        if not isinstance(buys_raw, list) or not isinstance(sells_raw, list):
            return None

        pair_info = reverse_map.get(pair_id)
        if pair_info is None:
            return None

        quote_sym, base_sym = pair_info

        # Find corresponding Quote and Base objects
        quote = None
        for q in quotes:
            if cls._get_quote_string(q) == quote_sym:
                quote = q
                break
        if quote is None:
            return None

        base = None
        for b in bases:
            if b.value.upper() == base_sym:
                base = b
                break
        if base is None:
            return None

        bids_list = cls._build_order_list(buys_raw, quote, base, now)
        asks_list = cls._build_order_list(sells_raw, quote, base, now)

        if not bids_list and not asks_list:
            return None

        return OrderBook(asks=asks_list, bids=bids_list)

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        """
        P2P: fetch all orderbooks using the batch endpoint, filter by needed pair IDs.
        Uses the same pair_id mapping as OTC.
        """
        forward_map, reverse_map = await cls._fetch_pairs_map()
        if not forward_map or not reverse_map:
            return OrderBooks()

        needed_pair_ids = cls._get_needed_pair_ids(quotes, bases, forward_map)
        if not needed_pair_ids:
            return OrderBooks()

        try:
            data = await get_json("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/buys_sells")
        except (OSError, ValueError, TimeoutError):
            return OrderBooks()

        final_result = OrderBooks()
        now = datetime.datetime.now(datetime.timezone.utc)

        for pair_id_str, order_data in data.items():
            pair_id = int(pair_id_str)
            if pair_id not in needed_pair_ids:
                continue

            ob = cls._process_orderbook_entry(pair_id, order_data, reverse_map, quotes, bases, now)
            if ob is not None:
                final_result.upsert(ob)

        return final_result