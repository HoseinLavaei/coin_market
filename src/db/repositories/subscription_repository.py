"""
Repository for unified subscriptions – CRUD, pending, and sync versions for Celery.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, select, update, delete, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import or_

from ..database import AsyncSessionLocal
from ..helpers import now_minutes, now_seconds
from ..models import Subscription
from ...environment import DATABASE_URL


# ─── Async versions (for bots) ──────────────────────────────

async def get_subscription_for_user(user_id: int) -> Optional[Subscription]:
    """Get the subscription (active or pending) for a given user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def get_active_subscription_for_user(user_id: int) -> Optional[Subscription]:
    """Get only the active subscription (chat_id NOT NULL) for a user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.chat_id.is_not(None)
            )
        )
        return result.scalar_one_or_none()


async def get_pending_by_key(key: str) -> Optional[Subscription]:
    """Fetch a pending subscription by its activation key (still valid)."""
    now = now_seconds()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.activation_key == key,
                Subscription.expires_at > now,
                Subscription.chat_id.is_(None)  # ensure pending
            )
        )
        return result.scalar_one_or_none()


async def create_or_replace_pending(
    user_id: int,
    provider: str | None,
    type_filter: str | None,
    volume: Decimal | None,
    repeat_interval: int,
    key: str,
    expires_at: int,
) -> Subscription:
    """
    Create a new pending subscription, or replace an existing one (active or pending)
    for the same user.
    """
    async with AsyncSessionLocal() as session:
        # Check if a row exists for this user
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            # Update all fields – make it pending
            existing.chat_id = None
            existing.provider = provider
            existing.type_filter = type_filter
            existing.volume = volume
            existing.repeat_interval = repeat_interval
            existing.last_sent_at = None
            existing.activation_key = key
            existing.expires_at = expires_at
            # updated_at will auto‑update
            await session.commit()
            await session.refresh(existing)
            return existing
        else:
            new_sub = Subscription(
                user_id=user_id,
                chat_id=None,
                provider=provider,
                type_filter=type_filter,
                volume=volume,
                repeat_interval=repeat_interval,
                last_sent_at=None,
                activation_key=key,
                expires_at=expires_at,
            )
            session.add(new_sub)
            await session.commit()
            await session.refresh(new_sub)
            return new_sub


async def claim_subscription_by_key(key: str, chat_id: int) -> dict | None:
    """
    Claim a pending subscription by key.
    Returns the subscription data needed to send the first update, or None if invalid.
    """
    now = now_seconds()
    async with AsyncSessionLocal() as session:
        # Use row lock to prevent race conditions
        stmt = select(Subscription).where(
            Subscription.activation_key == key,
            Subscription.expires_at > now,
            Subscription.chat_id.is_(None)
        ).with_for_update()
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()

        if not sub:
            return None

        # Activate: set chat_id, clear key/expires, reset last_sent_at
        sub.chat_id = chat_id
        sub.activation_key = None
        sub.expires_at = None
        sub.last_sent_at = None   # so first update is sent immediately
        await session.commit()
        await session.refresh(sub)

        return {
            "user_id": sub.user_id,
            "provider": sub.provider,
            "type_filter": sub.type_filter,
            "volume": sub.volume,
            "repeat_interval": sub.repeat_interval,
            "chat_id": chat_id,
        }


async def update_active_subscription(
    user_id: int,
    provider: str | None,
    type_filter: str | None,
    volume: Decimal | None,
    repeat_interval: int,
) -> Subscription:
    """
    Update an existing ACTIVE subscription (chat_id NOT NULL) without creating a pending.
    Used when user edits their subscription while already active.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.chat_id.is_not(None)
        ).with_for_update()
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()

        if not sub:
            raise ValueError("No active subscription found for this user")

        sub.provider = provider
        sub.type_filter = type_filter
        sub.volume = volume
        sub.repeat_interval = repeat_interval
        sub.last_sent_at = None   # force immediate next update
        await session.commit()
        await session.refresh(sub)
        return sub


async def delete_subscription(user_id: int) -> int:
    """Delete a subscription (active or pending) by user_id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subscription).where(Subscription.user_id == user_id)
        )
        await session.commit()
        return result.rowcount


# ─── Async versions for Celery (optional, but we keep the sync ones) ──

async def get_due_subscriptions() -> list[Subscription]:
    """Async version – only active subscriptions (chat_id NOT NULL)."""
    now = now_minutes()
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription).where(
            Subscription.chat_id.is_not(None),
            or_(
                Subscription.last_sent_at.is_(None),
                (Subscription.last_sent_at + Subscription.repeat_interval) <= now
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def update_last_sent_at(sub_id: int) -> None:
    now = now_minutes()
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(last_sent_at=now)
        )
        await session.commit()


# ─── Sync versions (for Celery tasks) ────────────────────────

def _get_sync_database_url() -> str:
    """Convert asyncpg URL to sync psycopg2 URL."""
    if DATABASE_URL.startswith("postgresql+asyncpg://"):
        return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return DATABASE_URL


_sync_engine = create_engine(_get_sync_database_url(), pool_pre_ping=True)
_SyncSessionLocal = sessionmaker(bind=_sync_engine)


def get_due_subscriptions_sync() -> list[dict]:
    """Sync version – only active subscriptions."""
    now_min = now_minutes()
    session = _SyncSessionLocal()
    try:
        result = session.execute(
            text("""
                 SELECT id, chat_id, provider, type_filter, volume, repeat_interval
                 FROM subscriptions
                 WHERE chat_id IS NOT NULL
                 AND (last_sent_at IS NULL OR last_sent_at + repeat_interval <= :now)
                 """),
            {"now": now_min}
        )
        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "chat_id": row[1],
                "provider": row[2],
                "type_filter": row[3],
                "volume": row[4],
                "repeat_interval": row[5],
            }
            for row in rows
        ]
    finally:
        session.close()


def update_last_sent_at_sync(sub_id: int) -> None:
    """Sync version."""
    now_min = now_minutes()
    session = _SyncSessionLocal()
    try:
        session.execute(
            text("UPDATE subscriptions SET last_sent_at = :now WHERE id = :id"),
            {"now": now_min, "id": sub_id}
        )
        session.commit()
    finally:
        session.close()