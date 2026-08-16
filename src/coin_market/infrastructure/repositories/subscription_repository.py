"""
Repository for managing Subscriptions and PendingSubscriptions in the database.
Uses SQLAlchemy async sessions and handles the two‑step activation flow.
"""

from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import select, update, delete, and_

from ..database import AsyncSessionLocal
from ..models import Subscription, PendingSubscription
from ...environment import TIMEZONE


async def add_subscription(
        chat_id: int,
        user_id: int,
        provider: str | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
        repeat_interval: int | None = None,
) -> Subscription:
    """Create a new active subscription for a chat."""
    async with AsyncSessionLocal() as session:
        sub = Subscription(
            chat_id=chat_id,
            user_id=user_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            status="active",
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


async def get_subscriptions_for_user(user_id: int) -> list[Subscription]:
    """Return all subscriptions (any status) belonging to a user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
        return list(result.scalars().all())


async def get_active_subscriptions() -> list[Subscription]:
    """Return all active subscriptions that have a repeat_interval set."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                and_(Subscription.status == "active", Subscription.repeat_interval.is_not(None))
            )
        )
        return list(result.scalars().all())


async def pause_subscription_by_id(sub_id: int, user_id: int) -> int:
    """Pause a subscription (set status to 'paused'). Returns number of affected rows."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(and_(Subscription.id == sub_id, Subscription.user_id == user_id))
            .values(status="paused", updated_at=datetime.now())
        )
        await session.commit()
        return result.rowcount


async def resume_subscription_by_id(sub_id: int, user_id: int) -> int:
    """
    Resume a paused subscription (set status to 'active').
    Returns number of affected rows.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(and_(Subscription.id == sub_id, Subscription.user_id == user_id, Subscription.status == "paused"))
            .values(status="active", updated_at=datetime.now())
        )
        await session.commit()
        return result.rowcount


async def delete_subscription_by_id(sub_id: int, user_id: int) -> int:
    """Permanently delete a subscription. Returns number of affected rows."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subscription).where(and_(Subscription.id == sub_id, Subscription.user_id == user_id))
        )
        await session.commit()
        return result.rowcount


async def create_pending_subscription(
        key: str,
        user_id: int,
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int | None,
        expires_at: datetime,
) -> PendingSubscription:
    """Create a pending subscription with a one‑time activation key."""
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
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingSubscription).where(PendingSubscription.key == key).with_for_update()
        )
        pending = result.scalar_one_or_none()
        if pending is None:
            return None
        pending = cast(PendingSubscription, pending)
        if pending.status != "pending":
            return None
        if pending.expires_at < datetime.now(TIMEZONE):
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
        await session.execute(delete(PendingSubscription).where(PendingSubscription.key == key))
        await session.commit()
