from datetime import datetime, tzinfo
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from .provider_name import ProviderName


class Quote(Enum):
    RLS = "RLS"
    USD = "USD"
    EUR = "EUR"

    def __str__(self) -> str:
        return self.name

    def get_symbol(self) -> str:
        match self:
            case self.RLS:
                return "RIAL"
            case self.USD:
                return "$"
            case self.EUR:
                return "€"
    @classmethod
    def from_symbol(cls, data: str) -> "Quote":
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
    base: str
    buy_price: Decimal
    sell_price: Decimal
    quote: Quote
    timestamp: datetime

    model_config = {"frozen": True}

    
    def __str__(self) -> str:
        formatted_buy = f"{self.buy_price:,}"
        formatted_sell = f"{self.sell_price:,}"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.provider}'s {self.base} : Buy: {formatted_buy} {self.quote.get_symbol()} , Sell: {formatted_sell} {self.quote.get_symbol()}"

    def to_timezone(self, tz:tzinfo) -> "Coin":
        """Returns a new Coin instance with the timestamp converted to the given timezone."""
        return self.model_copy(update={"timestamp": self.timestamp.astimezone(tz)})

    def serialize(self) -> str:
        timestamp_str = self.timestamp.isoformat() if self.timestamp else ""
        return f"{self.provider.name}|{self.base}|{self.buy_price}|{self.sell_price}|{self.quote.get_symbol()}|{timestamp_str}"
    @classmethod
    def deserialize(cls, data: str) -> "Coin":
        parts = data.split("|")
        if len(parts) < 5:
            raise ValueError(f"Invalid coin data: {data}")

        provider = ProviderName[parts[0]]
        symbol = parts[1]
        buy_price = Decimal(parts[2])
        sell_price = Decimal(parts[3])
        currency_symbol = parts[4]
        timestamp = datetime.fromisoformat(parts[5])

        currency = Quote.from_symbol(currency_symbol)

        return cls(
            provider=provider,
            base=symbol,
            buy_price=buy_price,
            sell_price=sell_price,
            quote=currency,
            timestamp=timestamp
        )


class Coins(BaseModel):
    """Collection of coins from a specific provider and currency.
    
    Acts as a dictionary with symbol keys for easy access.
    """
    coins: dict[str, Coin] = Field(default_factory=dict)  # the key is f"{provider_name}:{quote}:{base}"

    @classmethod
    def from_list(cls, data: list[dict]) -> Coins:
        """Create a Coins collection from a list of coin data dictionaries."""
        coins = cls()

        for coin_data in data:
            coins.upsert(Coin.model_validate(coin_data))

        return coins

    @staticmethod
    def get_key_from_details(provider: ProviderName, quote: Quote, base: str) -> str:
        return f"{provider}:{quote}:{base}"

    def get(self, provider: ProviderName, quote: Quote, base: str) -> Coin | None:
        """Get a coin by symbol using bracket notation (coins['BTC'])."""
        return self.coins.get(Coins.get_key_from_details(provider, quote, base))

    def upsert(self, coin: Coin) -> None:
        """Add or update a coin in the collection."""
        self.coins[Coins.get_key_from_details(coin.provider, coin.quote, coin.base)] = coin

    def remove(self, provider: ProviderName, quote: Quote, base: str) -> None:
        """Remove a coin from the collection by symbol."""
        del self.coins[Coins.get_key_from_details(provider, quote, base)]

    def contains(self, provider: ProviderName, quote: Quote, base: str) -> bool:
        """Check if a coin symbol exists in the collection."""
        return Coins.get_key_from_details(provider, quote, base) in self.coins

    def find_by_base(self, base: str) -> list[Coin]:
        """Find all coins with the specified base currency."""
        return [coin for coin in self.coins.values() if coin.base.upper() == base.upper()]

    def __len__(self) -> int:
        """Return the number of coins in the collection."""
        return len(self.coins)

    def __str__(self) -> str:
        if not self.coins:
            return (
                f"(No coins)"
            )

        return "\n\n".join(str(coin) for coin in self.coins.values())
    def serialize(self) -> str:
        output = ""
        for coin in self.coins.values():
            output += f"{coin.__repr__()}\n"
        return output.strip()
    @classmethod
    def deserialize(cls, data: str) -> "Coins":
        lines = data.split("\n")
        coins = cls()
        for line in lines:
            coins.upsert(Coin.deserialize(line))
        return coins