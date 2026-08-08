import json
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from .provider_name import ProviderName
from .environment import TIMEZONE


class Base(Enum):
    USDT = "USDT"
    BTC = "BTC"


class Quote(Enum):
    RLS = "RLS"
    USD = "USD"
    EUR = "EUR"

    def get_symbol(self) -> str:
        match self:
            case self.RLS:
                return "RIAL"
            case self.USD:
                return "$"
            case self.EUR:
                return "€"

    @classmethod
    def from_symbol(cls, data: str) -> Quote:
        match data:
            case "RIAL":
                return cls.RLS
            case "$":
                return cls.USD
            case "€":
                return cls.EUR
            case _:
                raise ValueError(f"Invalid currency symbol: {data}")


class Coin(BaseModel):
    provider: ProviderName
    base: Base
    buy_price: Decimal
    sell_price: Decimal
    quote: Quote
    timestamp: datetime

    model_config = {"frozen": True}

    def __str__(self) -> str:
        formatted_buy = f"{self.buy_price:,}"
        formatted_sell = f"{self.sell_price:,}"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.provider.value}'s {self.base.value} : Buy: {formatted_buy} {self.quote.get_symbol()} , Sell: {formatted_sell} {self.quote.get_symbol()}"

    def to_timezone(self) -> Coin:
        return self.model_copy(update={"timestamp": self.timestamp.astimezone(TIMEZONE)})
    def apply_fee(self, buy_fee:Decimal, sell_fee:Decimal) -> Coin:
        return self.model_copy(update={"buy_price": self.buy_price * (1+buy_fee), "sell_price": self.sell_price * (1-sell_fee)})
    # ---------- Serialization ----------
    def to_dict(self) -> dict:
        return {
            "provider": self.provider.name,
            "base": self.base.name,
            "buy_price": str(self.buy_price),
            "sell_price": str(self.sell_price),
            "quote": self.quote.name,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Coin:
        return cls(
            provider=ProviderName[data["provider"]],
            base=Base[data["base"]],
            buy_price=Decimal(data["buy_price"]),
            sell_price=Decimal(data["sell_price"]),
            quote=Quote[data["quote"]],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class Order(BaseModel):
    coin: Coin
    quantity: Decimal

    def to_timezone(self) -> Order:
        return Order(coin=self.coin.to_timezone(), quantity=self.quantity)

    def __str__(self) -> str:
        return f"{self.coin}, {self.quantity} available"

    def apply_fee(self, buy_fee:Decimal, sell_fee:Decimal) -> Order:
        return Order(coin=self.coin.apply_fee(buy_fee, sell_fee),quantity=self.quantity)
    # ---------- Serialization ----------
    def to_dict(self) -> dict:
        return {
            "coin": self.coin.to_dict(),
            "quantity": str(self.quantity),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Order:
        return cls(
            coin=Coin.from_dict(data["coin"]),
            quantity=Decimal(data["quantity"]),
        )


def _calculate_weighted_average(orders: list[Order], volume: Decimal, side: str) -> Decimal:
    total_value = Decimal('0')
    total_volume = Decimal('0')
    remaining = volume

    for order in orders:
        if remaining <= 0:
            break
        take = min(order.quantity, remaining)
        price = order.coin.sell_price if side == "buy" else order.coin.buy_price
        total_value += price * take
        total_volume += take
        remaining -= take

    if total_volume == 0:
        raise ValueError(f"No volume available in {side}s")
    return total_value / total_volume


class OrderBook(BaseModel):
    asks: list[Order]
    bids: list[Order]

    def get_by_volume(self, volume: Decimal) -> Coin:
        if not self.asks or not self.bids:
            raise ValueError("Order book is empty on one or both sides")
        if volume <= 0:
            raise ValueError("Volume must be positive")

        avg_buy = _calculate_weighted_average(self.asks, volume, "buy")
        avg_sell = _calculate_weighted_average(self.bids, volume, "sell")

        first_coin = self.asks[0].coin if self.asks else self.bids[0].coin
        return Coin(
            provider=first_coin.provider,
            base=first_coin.base,
            buy_price=avg_buy,
            sell_price=avg_sell,
            quote=first_coin.quote,
            timestamp=first_coin.timestamp
        )

    def get_provider(self) -> ProviderName:
        if self.asks:
            return self.asks[0].coin.provider
        elif self.bids:
            return self.bids[0].coin.provider
        else:
            raise ValueError("Order book is empty")

    def get_quote(self) -> Quote:
        if self.asks:
            return self.asks[0].coin.quote
        elif self.bids:
            return self.bids[0].coin.quote
        else:
            raise ValueError("Order book is empty")

    def get_base(self) -> Base:
        if self.asks:
            return self.asks[0].coin.base
        elif self.bids:
            return self.bids[0].coin.base
        else:
            raise ValueError("Order book is empty")

    def to_timezone(self) -> OrderBook:
        new_asks = [order.to_timezone() for order in self.asks]
        new_bids = [order.to_timezone() for order in self.bids]
        return OrderBook(asks=new_asks, bids=new_bids)

    def apply_fee(self, buy_fee:Decimal, sell_fee:Decimal) -> OrderBook:
        new_asks = [order.apply_fee(buy_fee, sell_fee) for order in self.asks]
        new_bids = [order.apply_fee(buy_fee, sell_fee) for order in self.bids]
        return OrderBook(asks=new_asks, bids=new_bids)
    def to_string(self, volume: Decimal) -> str:
        if not self.asks and not self.bids:
            return "OrderBook(empty)"

        total_ask_vol = sum(order.quantity for order in self.asks)
        total_bid_vol = sum(order.quantity for order in self.bids)

        summary = (
            f"OrderBook (asks: {len(self.asks)} levels, total vol: {total_ask_vol:.4f} | "
            f"bids: {len(self.bids)} levels, total vol: {total_bid_vol:.4f})"
        )

        # Catch only ValueError (raised by get_by_volume when no volume available)
        try:
            vwap_coin = self.get_by_volume(volume)
            return f"{summary}\n  VWAP for 1.0 base: {vwap_coin}"
        except ValueError:
            best_ask = self.asks[0].coin.sell_price if self.asks else None
            best_bid = self.bids[0].coin.buy_price if self.bids else None
            return f"{summary}\n  Best Ask: {best_ask}, Best Bid: {best_bid}"

    def __str__(self) -> str:
        return self.to_string(Decimal(1))

    # ---------- Serialization ----------
    def to_dict(self) -> dict:
        return {
            "asks": [order.to_dict() for order in self.asks],
            "bids": [order.to_dict() for order in self.bids],
        }

    @classmethod
    def from_dict(cls, data: dict) -> OrderBook:
        return cls(
            asks=[Order.from_dict(order_data) for order_data in data["asks"]],
            bids=[Order.from_dict(order_data) for order_data in data["bids"]],
        )


class Coins(BaseModel):
    coins: dict[tuple[ProviderName, Quote, Base], Coin] = Field(default_factory=dict)

    def upsert(self, coin: Coin) -> None:
        key = self.get_key_from_details(coin.provider, coin.quote, coin.base)
        self.coins[key] = coin

    @staticmethod
    def get_key_from_details(provider: ProviderName, quote: Quote, base: Base) -> tuple[ProviderName, Quote, Base]:
        return provider, quote, base

    def to_timezone(self) -> Coins:
        result = Coins()
        for coin in self.coins.values():
            result.upsert(coin.to_timezone())
        return result

    def apply_fee(self, buy_fee:Decimal, sell_fee:Decimal) -> Coins:
        return Coins(coins={key:value.apply_fee(buy_fee, sell_fee) for key, value in self.coins.items()})

    def __str__(self) -> str:
        if not self.coins:
            return "(No coins)"
        return "\n\n".join(str(coin) for coin in self.coins.values())

    # ---------- Serialization ----------
    def to_json(self) -> str:
        return json.dumps([coin.to_dict() for coin in self.coins.values()])

    @classmethod
    def from_json(cls, json_str: str) -> Coins:
        coin_dicts = json.loads(json_str)
        coins = Coins()
        for coin_dict in coin_dicts:
            coins.upsert(Coin.from_dict(coin_dict))
        return coins


class OrderBooks(BaseModel):
    books: dict[tuple[ProviderName, Quote, Base], OrderBook] = Field(default_factory=dict)

    def upsert(self, book: OrderBook) -> None:
        key = self.get_key_from_details(
            book.get_provider(),
            book.get_quote(),
            book.get_base()
        )
        self.books[key] = book

    @staticmethod
    def get_key_from_details(provider: ProviderName, quote: Quote, base: Base) -> tuple[ProviderName, Quote, Base]:
        return provider, quote, base

    def to_timezone(self) -> OrderBooks:
        result = OrderBooks()
        for book in self.books.values():
            result.upsert(book.to_timezone())
        return result

    def apply_fee(self, buy_fee:Decimal, sell_fee:Decimal) -> OrderBooks:
        return OrderBooks(books={key:value.apply_fee(buy_fee, sell_fee) for key, value in self.books.items()})

    def to_string(self, volume: Decimal) -> str:
        if not self.books:
            return "OrderBooks(empty)"
        lines = []
        for (provider, quote, base), book in self.books.items():
            book_str = book.to_string(volume).replace("\n", "\n  ")
            lines.append(f"{provider.value}/{quote.value}/{base.value}:\n  {book_str}")
        return "OrderBooks:\n" + "\n\n".join(lines)

    def __str__(self) -> str:
        return self.to_string(Decimal(1))

    # ---------- Serialization ----------
    def to_json(self) -> str:
        return json.dumps([book.to_dict() for book in self.books.values()])

    @classmethod
    def from_json(cls, json_str: str) -> OrderBooks:
        book_dicts = json.loads(json_str)
        books = OrderBooks()
        for book_dict in book_dicts:
            books.upsert(OrderBook.from_dict(book_dict))
        return books
