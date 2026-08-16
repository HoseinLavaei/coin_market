"""
Manages the global cache of market data: loading from DB on startup,
periodic updates from exchange APIs, and saving snapshots.
"""

from datetime import datetime

from .data_provider import update_cache_data
from .fetcher import fetch_all
from .subscription_scheduler import reload_subscriptions
from ..environment import TIMEZONE
from ..infrastructure.repositories import load_latest_snapshot, save_snapshot


async def load_cache_from_db() -> None:
    """
    Load the most recent snapshot from the database and store it in the global cache.
    Logs the number of coins and orderbooks loaded, or indicates if no data exists.
    """
    snapshot = await load_latest_snapshot()
    if snapshot:
        coins, orderbooks = snapshot
        updated_at = datetime.now(TIMEZONE)
        update_cache_data(coins, orderbooks, updated_at)
        timestamp = updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Loaded {len(coins.coins)} coins and {len(orderbooks.books)} orderbooks from DB.")
    else:
        print("No previous data in database. Will fetch on first update.")


async def update_cache(context) -> None:
    """
    Fetch fresh data from all providers, update the global cache,
    save the snapshot to the database, and reload subscriptions.
    Called periodically by the broadcast bot's job queue.
    """
    try:
        coins, books = await fetch_all()
        updated_at = datetime.now(TIMEZONE)
        update_cache_data(coins, books, updated_at)
        await save_snapshot(coins, books)
        timestamp = updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated and saved to DB.")
        await reload_subscriptions(context)
    except Exception as e:
        print(f"Cache update failed: {e}")
