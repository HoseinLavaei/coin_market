"""
Enums for the coin market system.
"""

from enum import Enum


class ProviderName(Enum):
    """Supported exchange providers."""
    ABAN_TETHER = "ABAN_TETHER"
    BITPIN = "BITPIN"
    EXIR = "EXIR"
    NOBITEX = "NOBITEX"
    RAMZINEX = "RAMZINEX"
    WALLEX = "WALLEX"
    TABDEAL = "TABDEAL"
    OMPFINEX = "OMPFINEX"
    OKEX = "OKEX"


class Base(Enum):
    """Base currencies (the asset being traded)."""
    USDT = "USDT"
    BTC = "BTC"


class Quote(Enum):
    """Quote currencies (the currency used for pricing)."""
    TMN = "TMN"
    USD = "USD"
    EUR = "EUR"
