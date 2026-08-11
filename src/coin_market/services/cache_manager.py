from datetime import datetime
from ..environment import TIMEZONE
from ..infrastructure.repositories import load_latest_snapshot, save_snapshot
from .fetcher import fetch_all
from .subscription_scheduler import reload_subscriptions  # safe: no circular import now
from .data_provider import update_cache_data


async def load_cache_from_db() -> None:
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