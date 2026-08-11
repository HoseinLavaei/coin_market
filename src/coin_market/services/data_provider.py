from datetime import datetime
from ..domain import Coins, OrderBooks
from ..environment import TIMEZONE

# Global cache state (moved here)
_cached_coins: Coins = Coins()
_cached_orderbooks: OrderBooks = OrderBooks()
_cache_updated_at = datetime.now(TIMEZONE)


def get_cached_data() -> tuple[Coins, OrderBooks, datetime]:
    """Return the current cached market data."""
    return _cached_coins, _cached_orderbooks, _cache_updated_at


def update_cache_data(coins: Coins, orderbooks: OrderBooks, updated_at: datetime) -> None:
    """Update the global cache state."""
    global _cached_coins, _cached_orderbooks, _cache_updated_at
    _cached_coins = coins
    _cached_orderbooks = orderbooks
    _cache_updated_at = updated_at