import json
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .enums import ProviderName, Base, Quote
from .value_objects import indent_text
from ..environment import TIMEZONE


class Coin(BaseModel):
    provider: ProviderName
    base: Base
    quote: Quote
    raw_buy_price: Decimal          # was _buy_price
    raw_sell_price: Decimal         # was _sell_price
    buy_fee: Decimal
    sell_fee: Decimal
    timestamp: datetime

    @property
    def buy_price(self) -> Decimal:
        return self.raw_buy_price / (Decimal('1') - self.buy_fee / 100)

    @property
    def sell_price(self) -> Decimal:
        return self.raw_sell_price / (Decimal('1') + self.sell_fee / 100)

    def get_formatted_price(self) -> tuple[str, str]:
        formatted_buy = f"{int(self.buy_price):,}"
        formatted_sell = f"{int(self.sell_price):,}"
        return formatted_buy, formatted_sell

    def __str__(self) -> str:
        formatted_buy, formatted_sell = self.get_formatted_price()
        return f"🟢 Buy: {formatted_buy} 🔴 Sell: {formatted_sell}"

    def to_timezone(self) -> "Coin":
        return self.model_copy(update={"timestamp": self.timestamp.astimezone(TIMEZONE)})

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.name,
            "base": self.base.name,
            "quote": self.quote.name,
            "raw_buy_price": str(self.raw_buy_price),
            "raw_sell_price": str(self.raw_sell_price),
            "buy_fee": str(self.buy_fee),
            "sell_fee": str(self.sell_fee),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Coin":
        return cls(
            provider=ProviderName[data["provider"]],
            base=Base[data["base"]],
            quote=Quote[data["quote"]],
            raw_buy_price=Decimal(data["raw_buy_price"]),
            raw_sell_price=Decimal(data["raw_sell_price"]),
            buy_fee=Decimal(data["buy_fee"]),
            sell_fee=Decimal(data["sell_fee"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )

class Order(BaseModel):
    coin: Coin
    quantity: Decimal

    def to_timezone(self) -> "Order":
        return Order(coin=self.coin.to_timezone(), quantity=self.quantity)

    def __str__(self) -> str:
        price_str, _ = self.coin.get_formatted_price()
        return f"📊 {self.coin.base.value} @ {price_str} | 📦 Vol: {self.quantity:,.2f} {self.coin.base.value}"

    def to_dict(self) -> dict:
        return {
            "coin": self.coin.to_dict(),
            "quantity": str(self.quantity),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
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
            quote=first_coin.quote,
            raw_buy_price=avg_buy,
            raw_sell_price=avg_sell,
            buy_fee=first_coin.buy_fee,
            sell_fee=first_coin.sell_fee,
            timestamp=first_coin.timestamp,
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

    def to_timezone(self) -> "OrderBook":
        return OrderBook(
            asks=[order.to_timezone() for order in self.asks],
            bids=[order.to_timezone() for order in self.bids],
        )

    def to_string(self, volume: Decimal) -> str:
        if not self.asks or not self.bids:
            return "📭 P2P: (No data)"
        try:
            coin = self.get_by_volume(volume)
            return str(coin)
        except ValueError:
            return "📭 P2P: (No data)"

    def __str__(self) -> str:
        return self.to_string(Decimal(1))

    def to_dict(self) -> dict:
        return {
            "asks": [order.to_dict() for order in self.asks],
            "bids": [order.to_dict() for order in self.bids],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderBook":
        return cls(
            asks=[Order.from_dict(order_data) for order_data in data["asks"]],
            bids=[Order.from_dict(order_data) for order_data in data["bids"]],
        )


class Coins(BaseModel):
    coins: dict[tuple[ProviderName, Quote, Base], Coin] = Field(default_factory=dict)

    def upsert(self, coin: Coin) -> None:
        key = (coin.provider, coin.quote, coin.base)
        self.coins[key] = coin

    def to_timezone(self) -> "Coins":
        result = Coins()
        for coin in self.coins.values():
            result.upsert(coin.to_timezone())
        return result

    def __str__(self) -> str:
        if not self.coins:
            return "💰 OTC prices:  (No coins)"
        content = "\n\n".join(str(coin) for coin in self.coins.values())
        indented = indent_text(content, spaces=4)
        return f"💰 OTC prices:\n{indented}"

    def to_json(self) -> str:
        return json.dumps([coin.to_dict() for coin in self.coins.values()])

    @classmethod
    def from_json(cls, json_str: str) -> "Coins":
        coin_dicts = json.loads(json_str)
        coins = Coins()
        for coin_dict in coin_dicts:
            coins.upsert(Coin.from_dict(coin_dict))
        return coins


class OrderBooks(BaseModel):
    books: dict[tuple[ProviderName, Quote, Base], OrderBook] = Field(default_factory=dict)

    def upsert(self, book: OrderBook) -> None:
        key = (book.get_provider(), book.get_quote(), book.get_base())
        self.books[key] = book

    def to_timezone(self) -> "OrderBooks":
        result = OrderBooks()
        for book in self.books.values():
            result.upsert(book.to_timezone())
        return result

    def to_string(self, volume: Decimal) -> str:
        if not self.books:
            return "🤝 P2P prices: (No order books)"
        lines = []
        for (provider, quote, base), book in self.books.items():
            book_str = indent_text(book.to_string(volume), 4)
            lines.append(f"📚 {provider.value}/{quote.value}/{base.value}:\n{book_str}")
        return "🤝 P2P prices:\n" + indent_text("\n\n".join(lines), 4)

    def __str__(self) -> str:
        return self.to_string(Decimal(1))

    def to_json(self) -> str:
        return json.dumps([book.to_dict() for book in self.books.values()])

    @classmethod
    def from_json(cls, json_str: str) -> "OrderBooks":
        book_dicts = json.loads(json_str)
        books = OrderBooks()
        for book_dict in book_dicts:
            books.upsert(OrderBook.from_dict(book_dict))
        return books
