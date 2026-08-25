"""
Repository for subscriptions – CRUD + get_due_subscriptions.
Includes sync versions for Celery tasks.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, select, update, delete, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import or_

from ..database import AsyncSessionLocal
from ..helpers import now_minutes
from ..models import Subscription
from ...environment import DATABASE_URL


# ─── Async versions (for bots) ──────────────────────────────

async def get_subscription_for_user(user_id: int) -> Optional[Subscription]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def add_or_replace_subscription(
        user_id: int,
        chat_id: int,
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int,
) -> Subscription:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        sub = existing.scalar_one_or_none()

        if sub is not None:
            sub.chat_id = chat_id
            sub.provider = provider
            sub.type_filter = type_filter
            sub.volume = volume
            sub.repeat_interval = repeat_interval
            sub.last_sent_at = None
            await session.commit()
            await session.refresh(sub)
            return sub

        new_sub = Subscription(
            user_id=user_id,
            chat_id=chat_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            last_sent_at=None,
        )
        session.add(new_sub)
        await session.commit()
        await session.refresh(new_sub)
        return new_sub


async def get_due_subscriptions() -> list[Subscription]:
    now = now_minutes()
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription).where(
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


async def delete_subscription(user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subscription).where(Subscription.user_id == user_id)
        )
        await session.commit()
        return result.rowcount


# ─── Sync versions (for Celery tasks) ────────────────────────

def _get_sync_database_url() -> str:
    """Convert asyncpg URL to sync psycopg2 URL."""
    if DATABASE_URL.startswith("postgresql+asyncpg://"):
        return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return DATABASE_URL


# Create a sync engine with psycopg2 (not asyncpg)
# This requires psycopg2-binary or psycopg2 to be installed.
_sync_engine = create_engine(_get_sync_database_url(), pool_pre_ping=True)
_SyncSessionLocal = sessionmaker(bind=_sync_engine)


def get_due_subscriptions_sync() -> list[dict]:
    """Sync version of get_due_subscriptions for Celery."""
    now_min = now_minutes()
    session = _SyncSessionLocal()
    try:
        result = session.execute(
            text("""
                 SELECT id, chat_id, provider, type_filter, volume, repeat_interval
                 FROM subscriptions
                 WHERE (last_sent_at IS NULL OR last_sent_at + repeat_interval <= :now)
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
    """Sync version of update_last_sent_at for Celery."""
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
