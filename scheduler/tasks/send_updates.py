"""
Celery task – fetches market data, sends updates to due subscriptions.
"""

import asyncio
from types import SimpleNamespace

from celery import shared_task

from src.broadcast.sender import send_to_subscription
from src.coins import fetch_all
from src.db import get_due_subscriptions_sync, update_last_sent_at_sync


@shared_task
def send_due_updates():
    """Entry point – runs the update cycle."""
    asyncio.run(_run_send_updates())


async def _run_send_updates():
    """Async implementation – fetches market data and sends updates."""
    print("Running send updates task...")

    # ─── 1. Fetch market data ──────────────────────────────
    coins, orderbooks = await fetch_all()
    # ─── 2. Get due subscriptions (sync DB) ────────────────
    subs = get_due_subscriptions_sync()
    print(f"Found {len(subs)} due subscriptions.")

    if not subs:
        return

    # ─── 3. Send updates ────────────────────────────────────
    for sub_data in subs:
        sub = SimpleNamespace(**sub_data)

        try:
            await send_to_subscription(sub, coins, orderbooks)
            update_last_sent_at_sync(sub.id)
            print(f"Sent update to subscription #{sub.id}")
        except Exception as e:
            print(f"Failed to send to subscription #{sub.id}: {e}")
