from typing import Protocol, runtime_checkable

import httpx

from ..enums import ProviderName, Quote, Base
from ..models import OrderBooks, Coins


async def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    """
    Perform an HTTP GET request and return the parsed JSON response.
    Raises RuntimeError on HTTP errors.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params or {}, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"API error: {e}") from e


@runtime_checkable
class Provider(Protocol):
    """
    Protocol defining the interface that all exchange providers must implement.
    Each provider fetches OTC prices and order books for the given trading pairs.
    """
    provider_name: ProviderName

    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins:
        ...

    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks:
        ...
