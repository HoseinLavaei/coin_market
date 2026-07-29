from datetime import datetime, tzinfo
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from .provider_name import ProviderName


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
    """Represents a cryptocurrency with market data.
    
    Frozen model to ensure immutability after creation.
    """
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

    def to_timezone(self, tz:tzinfo) -> "Coin":
        """Returns a new Coin instance with the timestamp converted to the given timezone."""
        return self.model_copy(update={"timestamp": self.timestamp.astimezone(tz)})

class Coins(BaseModel):
    """Collection of coins from a specific provider and currency.

    Acts as a dictionary with symbol keys for easy access.
    """
    coins: dict[tuple[ProviderName,Quote,Base],Coin] = Field(default_factory=dict)  # the key is f"{provider_name}:{quote}:{base}"

    def upsert(self, coin: Coin) -> None:
        key = self.get_key_from_details(coin.provider, coin.quote, coin.base)
        self.coins[key] = coin

    @staticmethod
    def get_key_from_details(provider: ProviderName, quote: Quote, base: Base) -> tuple[ProviderName,Quote,Base]:
        return provider, quote, base

    def to_timezone(self, tz:tzinfo) -> Coins:
        """Returns a new Coin instance with the timestamp converted to the given timezone."""
        result:Coins=Coins()
        for coin in self.coins.values():
            result.upsert(coin.to_timezone(tz))
        return result


    def __str__(self) -> str:
        if not self.coins:
            return (
                f"(No coins)"
            )

        return "\n\n".join(str(coin) for coin in self.coins.values())


class OrderBook(BaseModel):
    asks: list[tuple[Coin, Decimal]]
    bids: list[tuple[Coin, Decimal]]

    def get_by_volume(self, volume: Decimal) -> Coin:
        """
        Returns a Coin whose:
          - buy_price  = volume‑weighted average of the ASKS (what you pay when buying)
          - sell_price = volume‑weighted average of the BIDS (what you receive when selling)
        Consumes up to `volume` units from each side independently.
        If a side has insufficient liquidity, all available units are used.
        """
        if not self.asks or not self.bids:
            raise ValueError("Order book is empty on one or both sides")
        if volume <= 0:
            raise ValueError("Volume must be positive")

        # Average BUY price (consume ASKS)
        total_buy_value = Decimal('0')
        total_buy_volume = Decimal('0')
        remaining_buy = volume



        # TODO
        for coin, amount in self.asks:
            if remaining_buy <= 0:
                break
            take = min(amount, remaining_buy)
            total_buy_value += coin.sell_price * take
            total_buy_volume += take
            remaining_buy -= take

        if total_buy_volume == 0:
            raise ValueError("No volume available in asks")
        avg_buy = total_buy_value / total_buy_volume

        # Average SELL price (consume BIDS)
        total_sell_value = Decimal('0')
        total_sell_volume = Decimal('0')
        remaining_sell = volume

        for coin, amount in self.bids:
            if remaining_sell <= 0:
                break
            take = min(amount, remaining_sell)
            total_sell_value += coin.buy_price * take
            total_sell_volume += take
            remaining_sell -= take

        if total_sell_volume == 0:
            raise ValueError("No volume available in bids")
        avg_sell = total_sell_value / total_sell_volume

        # Build and return the result
        first_coin = self.asks[0][0] if self.asks else self.bids[0][0]
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
            return self.asks[0][0].provider
        elif self.bids:
            return self.bids[0][0].provider
        else:
            raise ValueError("Order book is empty")

    def get_quote(self) -> Quote:
        if self.asks:
            return self.asks[0][0].quote
        elif self.bids:
            return self.bids[0][0].quote
        else:
            raise ValueError("Order book is empty")

    def get_base(self) -> Base:
        if self.asks:
            return self.asks[0][0].base
        elif self.bids:
            return self.bids[0][0].base
        else:
            raise ValueError("Order book is empty")

    def to_timezone(self, tz: tzinfo) -> "OrderBook":
        """Returns a new OrderBook instance with all timestamps converted to the given timezone."""
        new_asks = [(coin.to_timezone(tz), amount) for coin, amount in self.asks]
        new_bids = [(coin.to_timezone(tz), amount) for coin, amount in self.bids]
        return OrderBook(asks=new_asks, bids=new_bids)

    def __str__(self) -> str:
        if not self.asks and not self.bids:
            return "OrderBook(empty)"

        total_ask_vol = sum(amt for _, amt in self.asks)
        total_bid_vol = sum(amt for _, amt in self.bids)

        # Base summary
        summary = (
            f"OrderBook (asks: {len(self.asks)} levels, total vol: {total_ask_vol:.4f} | "
            f"bids: {len(self.bids)} levels, total vol: {total_bid_vol:.4f})"
        )

        # Try to show VWAP for 1 unit of the base asset (e.g., 1 BTC, 1 USDT, etc.)
        try:
            vwap_coin = self.get_by_volume(Decimal('1'))
            return f"{summary}\n  VWAP for 1.0 base: {vwap_coin}"
        except Exception:
            # Fallback: show best bid/ask if VWAP fails (e.g., book has no volume)
            best_ask = self.asks[0][0].sell_price if self.asks else None
            best_bid = self.bids[0][0].buy_price if self.bids else None
            return f"{summary}\n  Best Ask: {best_ask}, Best Bid: {best_bid}"

class OrderBooks(BaseModel):
    books: dict[tuple[ProviderName, Quote, Base], OrderBook] = Field(default_factory=dict)

    def upsert(self, book: OrderBook) -> None:
        key = self.get_key_from_details(
            book.get_provider(),  # Now works with new OrderBook
            book.get_quote(),     # Now works with new OrderBook
            book.get_base()       # Now works with new OrderBook
        )
        self.books[key] = book

    @staticmethod
    def get_key_from_details(provider: ProviderName, quote: Quote, base: Base) -> tuple[ProviderName, Quote, Base]:
        return provider, quote, base

    def to_timezone(self, tz: tzinfo) -> "OrderBooks":
        """Returns a new OrderBooks instance with all timestamps converted to the given timezone."""
        result = OrderBooks()
        for book in self.books.values():
            result.upsert(book.to_timezone(tz))  # Now works with new OrderBook
        return result

    def __str__(self) -> str:
        if not self.books:
            return "OrderBooks(empty)"

        lines = []
        for (provider, quote, base), book in self.books.items():
            # Indent the multi-line book string
            book_str = str(book).replace("\n", "\n  ")
            lines.append(f"{provider.value}/{quote.value}/{base.value}:\n  {book_str}")
        return "OrderBooks:\n" + "\n\n".join(lines)