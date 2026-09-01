"""
Celery task – fetches market data, sends updates to due subscriptions.
"""

import asyncio

from celery import shared_task

from src import logger
from src.broadcast.sender import send_to_subscription
from src.coins import fetch_all
from src.db import get_due_subscriptions_sync, update_last_sent_at_sync
from src.subscription_types import SubscriptionData


@shared_task
def send_due_updates() -> None:
    """Entry point – runs the update cycle."""
    asyncio.run(_run_send_updates())


async def _run_send_updates() -> None:
    """Async implementation – fetches market data and sends updates."""
    logger.info("Running send updates task...")

    # ─── 1. Fetch market data ──────────────────────────────
    coins, orderbooks = await fetch_all()
    # ─── 2. Get due subscriptions (sync DB) ────────────────
    subs: list[SubscriptionData] = get_due_subscriptions_sync()
    logger.info(f"Found {len(subs)} due subscriptions.")

    if not subs:
        return

    # ─── 3. Send updates ────────────────────────────────────
    for sub in subs:
        try:
            await send_to_subscription(sub, coins, orderbooks)
            update_last_sent_at_sync(sub.id)
            logger.info(f"Sent update to subscription #{sub.id}")
        except Exception as e:
            logger.error(f"Failed to send to subscription #{sub.id}: {e}")
