"""
Repository for pending subscriptions – create, claim, and delete.
Uses BigInt timestamps (seconds since epoch) for expires_at.
"""

from decimal import Decimal

from sqlalchemy import select, delete

from ..database import AsyncSessionLocal
from ..helpers import now_seconds
from ..models import PendingSubscription


async def create_pending_subscription(
        key: str,
        user_id: int,
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int,
        expires_at: int,  # seconds since epoch
) -> PendingSubscription:
    """
    Create a pending subscription with a one‑time activation key.
    """
    async with AsyncSessionLocal() as session:
        pending = PendingSubscription(
            key=key,
            user_id=user_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            expires_at=expires_at,
            status="pending",
        )
        session.add(pending)
        await session.commit()
        await session.refresh(pending)
        return pending


async def claim_pending_subscription(key: str, chat_id: int) -> dict | None:
    """
    Claim a pending subscription by key. Validates that it is still pending and not expired.
    On success, marks it as claimed and returns the data needed to create a real subscription.
    """
    now = now_seconds()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingSubscription).where(PendingSubscription.key == key).with_for_update()
        )
        pending = result.scalar_one_or_none()

        if pending is None:
            return None

        if pending.status != "pending":
            return None

        if pending.expires_at < now:
            pending.status = "expired"
            await session.commit()
            return None

        pending.chat_id = chat_id
        pending.status = "claimed"
        await session.commit()

        return {
            "user_id": pending.user_id,
            "provider": pending.provider,
            "type_filter": pending.type_filter,
            "volume": pending.volume,
            "repeat_interval": pending.repeat_interval,
            "chat_id": chat_id,
        }


async def delete_pending_subscription(key: str) -> None:
    """Delete a pending subscription (used after successful activation)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PendingSubscription).where(PendingSubscription.key == key)
        )
        await session.commit()
