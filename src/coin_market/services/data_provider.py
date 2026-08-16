"""
Provides a central, global state for cached market data.
Other modules import get_cached_data() to read the current cache.
"""

from datetime import datetime

from ..domain import Coins, OrderBooks
from ..environment import TIMEZONE

# Global cache state
_cached_coins: Coins = Coins()
_cached_orderbooks: OrderBooks = OrderBooks()
_cache_updated_at = datetime.now(TIMEZONE)


def get_cached_data() -> tuple[Coins, OrderBooks, datetime]:
    """Return the current cached market data (coins, orderbooks, timestamp)."""
    return _cached_coins, _cached_orderbooks, _cache_updated_at


def update_cache_data(coins: Coins, orderbooks: OrderBooks, updated_at: datetime) -> None:
    """Replace the global cache state with fresh data."""
    global _cached_coins, _cached_orderbooks, _cache_updated_at
    _cached_coins = coins
    _cached_orderbooks = orderbooks
    _cache_updated_at = updated_at
