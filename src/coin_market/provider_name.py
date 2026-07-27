from enum import Enum


class ProviderName(Enum):
    ABAN_TETHER_OTC = "ABAN_TETHER_OTC"
    BITPIN_OTC = "BITPIN_OTC"
    BITPIN_P2P = "BITPIN_P2P"
    EXIR_P2P = "EXIR_P2P"
    NOBITEX_OTC = "NOBITEX_OTC"
    NOBITEX_P2P = "NOBITEX_P2P"
    RAMZINEX_OTC = "RAMZINEX_OTC"
    RAMZINEX_P2P = "RAMZINEX_P2P"
    WALLEX_OTC = "WALLEX_OTC"
    WALLEX_P2P = "WALLEX_P2P"

    def __str__(self) -> str:
        return self.name
