from enum import Enum


class ProviderName(Enum):
    ABAN_TETHER = "ABAN_TETHER"
    BITPIN = "BITPIN"
    EXIR = "EXIR"
    NOBITEX = "NOBITEX"
    RAMZINEX = "RAMZINEX"
    WALLEX = "WALLEX"

    def __str__(self) -> str:
        return self.name
