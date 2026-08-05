import os
import urllib.parse
from datetime import datetime

import asyncpg
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import select, update, delete, and_

from . import Coins, OrderBooks
from .subscription import Subscription
from .base import Base

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), primary_key=True, index=True)
    coins: Mapped[str] = mapped_column(JSONB, nullable=False)
    orderbooks: Mapped[str] = mapped_column(JSONB, nullable=False)


async def init_db():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")

        parsed = urllib.parse.urlparse(db_url)
        host = parsed.hostname
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        database = parsed.path.lstrip("/")

        conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)

        try:
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
                print("TimescaleDB extension is ready.")
            except Exception as e:
                print(f"Warning: Could not create TimescaleDB extension: {e}")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    timestamp TIMESTAMPTZ PRIMARY KEY,
                    coins JSONB NOT NULL,
                    orderbooks JSONB NOT NULL
                )
            """)
            print("market_snapshots table is ready")

            try:
                await conn.execute("""
                    SELECT create_hypertable('market_snapshots', 'timestamp', if_not_exists => TRUE)
                """)
                print("TimescaleDB hypertable for market_snapshots is ready")
            except asyncpg.UniqueViolationError:
                print("market_snapshots is already a hypertable")
            except Exception as e:
                print(f"Note: {e}")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    provider TEXT,
                    type_filter TEXT,
                    volume NUMERIC,
                    repeat_interval INT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            print("subscriptions table is ready")

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)
            """)
            print("subscriptions index is ready")

        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


# ─── Snapshot helpers ──────────────────────────────────────

async def load_latest_snapshot() -> tuple[Coins, OrderBooks] | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.select(MarketSnapshot)
            .order_by(MarketSnapshot.timestamp.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return None

        coins_data = getattr(snapshot, 'coins', '{}')
        orderbooks_data = getattr(snapshot, 'orderbooks', '{}')
        if not coins_data or not orderbooks_data:
            return None

        coins = Coins.from_json(coins_data)
        orderbooks = OrderBooks.from_json(orderbooks_data)
        return coins, orderbooks


async def save_snapshot(coins: Coins, orderbooks: OrderBooks) -> None:
    async with AsyncSessionLocal() as session:
        snapshot = MarketSnapshot(
            timestamp=datetime.now(),
            coins=coins.to_json(),
            orderbooks=orderbooks.to_json(),
        )
        session.add(snapshot)
        await session.commit()


# ─── Subscription helpers ──────────────────────────────────

async def add_subscription(
    chat_id: int,
    provider: str | None = None,
    type_filter: str | None = None,
    volume: float | None = None,
    repeat_interval: int | None = None,
) -> Subscription:
    async with AsyncSessionLocal() as session:
        sub = Subscription(
            chat_id=chat_id,
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


async def get_subscriptions_for_chat(chat_id: int) -> list[Subscription]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.chat_id == chat_id)
        )
        return list(result.scalars().all())


async def get_active_subscriptions() -> list[Subscription]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status == "active",
                    Subscription.repeat_interval.is_not(None)
                )
            )
        )
        return list(result.scalars().all())


async def pause_subscriptions_for_chat(chat_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(Subscription.chat_id == chat_id)
            .values(status="paused", updated_at=datetime.now())
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


async def resume_subscriptions_for_chat(chat_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(
                and_(
                    Subscription.chat_id == chat_id,
                    Subscription.status == "paused"
                )
            )
            .values(status="active", updated_at=datetime.now())
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


async def delete_subscriptions_for_chat(chat_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subscription)
            .where(Subscription.chat_id == chat_id)
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


async def close_db():
    await engine.dispose()