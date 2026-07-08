from decimal import Decimal
from typing import Any, Iterator

from pydantic import BaseModel, Field


def sort_key_with_nulls(value: Any, fallback: Any) -> tuple[int, Any]:
    """Returns a sort key tuple that places None values at the end.
    
    Used as a key function in sorted() to handle optional fields like rank and market_cap.
    """
    return value is None, value if value is not None else fallback


class Coin(BaseModel):
    """Represents a cryptocurrency with market data.
    
    Frozen model to ensure immutability after creation.
    """
    name: str
    symbol: str
    current_price: Decimal
    price_change_24h: Decimal | None = None
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    market_cap: Decimal | None = None
    volume_24h: Decimal | None = None
    circulating_supply: Decimal | None = None
    rank: int | None = None
    currency: str
    provider: str

    model_config = {"frozen": True}

    @property
    def is_gaining(self) -> bool:
        """True if the 24h price change is positive."""
        if self.price_change_24h is None:
            raise ValueError("Price change 24h is not available.")
        return self.price_change_24h > 0

    @property
    def is_losing(self) -> bool:
        """True if the 24h price change is negative."""
        if self.price_change_24h is None:
            raise ValueError("Price change 24h is not available.")
        return self.price_change_24h < 0

    def __str__(self) -> str:
        def format_decimal(value: Decimal, decimals: int = 2) -> str:
            """Format decimal with thousands separators and specified decimal places."""
            return f"{value:,.{decimals}f}"
        
        # Currency symbols
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "RLS": "IRT",  # Iranian Rial
        }
        symbol = currency_symbols.get(self.currency.upper(), self.currency)

        lines = [
            f"===== {self.provider} {self.name}/{self.currency} =====",
            f"Name: {self.name}",
            f"Symbol: {self.symbol}",
            f"Current Price: {symbol}{format_decimal(self.current_price)}",
        ]

        if self.price_change_24h is not None:
            lines.append(f"24h Change: {format_decimal(self.price_change_24h, 2)}%")

        if self.high_24h is not None:
            lines.append(f"24h High: {symbol}{format_decimal(self.high_24h)}")

        if self.low_24h is not None:
            lines.append(f"24h Low: {symbol}{format_decimal(self.low_24h)}")

        if self.market_cap is not None:
            lines.append(f"Market Cap: {symbol}{format_decimal(self.market_cap, 0)}")

        if self.volume_24h is not None:
            lines.append(f"24h Volume: {symbol}{format_decimal(self.volume_24h, 0)}")

        if self.circulating_supply is not None:
            lines.append(f"Circulating Supply: {format_decimal(self.circulating_supply, 0)}")

        if self.rank is not None:
            lines.append(f"Rank: #{self.rank}")

        return "\n".join(lines)


class Coins(BaseModel):
    """Collection of coins from a specific provider and currency.
    
    Acts as a dictionary with symbol keys for easy access.
    """
    coins: dict[str, Coin] = Field(default_factory=dict) # the key is f"{provider}:{currency}:{symbol}"

    @classmethod
    def from_list(cls, data: list[dict]) -> "Coins":
        """Create a Coins collection from a list of coin data dictionaries."""
        coins = cls()

        for coin_data in data:
            coins.upsert(Coin.model_validate(coin_data))

        return coins

    @staticmethod
    def get_key_from_details(provider:str, currency:str, symbol:str) -> str:
        return f"{provider}:{currency}:{symbol}"

    def get(self, provider:str, currency:str, symbol:str) -> Coin:
        """Get a coin by symbol using bracket notation (coins['BTC'])."""
        return self.coins[Coins.get_key_from_details(provider,currency,symbol)]

    def upsert(self, coin: Coin) -> None:
        """Add or update a coin in the collection."""
        self.coins[Coins.get_key_from_details(coin.provider,coin.currency,coin.symbol)] = coin

    def remove(self, provider:str, currency:str, symbol:str) -> None:
        """Remove a coin from the collection by symbol."""
        del self.coins[Coins.get_key_from_details(provider,currency,symbol)]


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

    def contains(self, provider:str, currency:str, symbol:str) -> bool:
        """Check if a coin symbol exists in the collection."""
        return Coins.get_key_from_details(provider,currency,symbol) in self.coins

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
