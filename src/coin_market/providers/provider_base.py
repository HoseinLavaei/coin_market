from typing import Protocol

import httpx

from .. import ProviderName
from ..coin import Coins, Quote


async def get_json(url: str, params: dict[str, str] | None = None) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params or {}, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"API error: {e}") from e


class Provider(Protocol):
    provider_name: ProviderName
    @classmethod
    async def fetch(cls, quote: Quote) -> Coins: ...