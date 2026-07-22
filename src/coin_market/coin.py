from decimal import Decimal
from enum import Enum
from typing import Any, Iterator
from pydantic import BaseModel, Field


class ProviderName(Enum):
    ABAN_TETHER = "ABAN_TETHER"
    BITPIN = "BITPIN"
    EXIR = "EXIR"
    NOBITEX = "NOBITEX"
    RAMZINEX = "RAMZINEX"
    WALLEX = "WALLEX"

    def __str__(self) -> str:
        return self.name

class Currency(Enum):
    RLS = 0
    USD = 1
    EUR = 2

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


def sort_key_with_nulls(value: Any, fallback: Any) -> tuple[int, Any]:
    """Returns a sort key tuple that places None values at the end.
    
    Used as a key function in sorted() to handle optional fields like rank and market_cap.
    """
    return value is None, value if value is not None else fallback


class Coin(BaseModel):
    """Represents a cryptocurrency with market data.
    
    Frozen model to ensure immutability after creation.
    """
    symbol: str
    current_price: Decimal
    currency: Currency
    provider: ProviderName

    model_config = {"frozen": True}

    def __str__(self) -> str:
        return f"{self.provider}'s {self.symbol} : {self.current_price}{self.currency.get_symbol()}"


class Coins(BaseModel):
    """Collection of coins from a specific provider and currency.
    
    Acts as a dictionary with symbol keys for easy access.
    """
    coins: dict[str, Coin] = Field(default_factory=dict)  # the key is f"{provider}:{currency}:{symbol}"

    @classmethod
    def from_list(cls, data: list[dict]) -> "Coins":
        """Create a Coins collection from a list of coin data dictionaries."""
        coins = cls()

        for coin_data in data:
            coins.upsert(Coin.model_validate(coin_data))

        return coins

    @staticmethod
    def get_key_from_details(provider: ProviderName, currency: Currency, symbol: str) -> str:
        return f"{provider}:{currency}:{symbol}"

    def get(self, provider: ProviderName, currency: Currency, symbol: str) -> Coin:
        """Get a coin by symbol using bracket notation (coins['BTC'])."""
        return self.coins[Coins.get_key_from_details(provider, currency, symbol)]

    def upsert(self, coin: Coin) -> None:
        """Add or update a coin in the collection."""
        self.coins[Coins.get_key_from_details(coin.provider, coin.currency, coin.symbol)] = coin

    def remove(self, provider: ProviderName, currency: Currency, symbol: str) -> None:
        """Remove a coin from the collection by symbol."""
        del self.coins[Coins.get_key_from_details(provider, currency, symbol)]

    def sorted_by_rank(self) -> list[Coin]:
        """Return coins sorted by rank (ascending), with None values last."""
        return sorted(
            self,
            key=lambda c: sort_key_with_nulls(c.rank, 0)
        )

    def sorted_by_market_cap(self) -> list[Coin]:
        """Return coins sorted by market cap (descending), with None values last."""
        return sorted(
            self,
            key=lambda c: sort_key_with_nulls(c.market_cap, Decimal(0)),
            reverse=True
        )

    def contains(self, provider: ProviderName, currency: Currency, symbol: str) -> bool:
        """Check if a coin symbol exists in the collection."""
        return Coins.get_key_from_details(provider, currency, symbol) in self.coins

    def __len__(self) -> int:
        """Return the number of coins in the collection."""
        return len(self.coins)

    def __iter__(self) -> Iterator[Coin]:
        """Iterate over all coins in the collection."""
        return iter(self.coins.values())

    def __str__(self) -> str:
        if not self.coins:
            return (
                f"(No coins)"
            )

        return (
                f"Number of coins: {len(self)}\n\n"
                + "\n\n".join(str(coin) for coin in self)
        )
