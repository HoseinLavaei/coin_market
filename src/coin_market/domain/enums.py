from enum import Enum


class ProviderName(Enum):
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
    USDT = "USDT"
    BTC = "BTC"


class Quote(Enum):
    TMN = "TMN"
    USD = "USD"
    EUR = "EUR"
