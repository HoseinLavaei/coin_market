from typing import Protocol, runtime_checkable
import httpx

from .. import ProviderName
from ..coin import Quote, Base, OrderBooks, Coins


async def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params or {}, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"API error: {e}") from e


@runtime_checkable
class Provider(Protocol):
    provider_name: ProviderName
    @classmethod
    async def get_otc(cls, quotes: list[Quote], bases: list[Base]) -> Coins: ...
    @classmethod
    async def get_orderbook(cls, quotes: list[Quote], bases: list[Base]) -> OrderBooks: ...
