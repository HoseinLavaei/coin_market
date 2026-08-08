import urllib.parse
from datetime import datetime
from decimal import Decimal
from typing import cast

import asyncpg
import sqlalchemy as sa
from sqlalchemy import select, update, delete, and_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from . import Coins, OrderBooks
from .base import Base
from .subscription import Subscription
from .environment import DATABASE_URL

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


# ─── Fee table ──────────────────────────────────────────────

class ProviderFee(Base):
    __tablename__ = "provider_fees"

    provider: Mapped[str] = mapped_column(sa.String, primary_key=True)
    buy_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    sell_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


async def init_db():
    try:
        parsed = urllib.parse.urlparse(DATABASE_URL)
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

            # market_snapshots
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

            # subscriptions
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    provider VARCHAR,
                    type_filter VARCHAR,
                    volume DECIMAL,
                    repeat_interval INT,
                    status VARCHAR DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT check_repeat_interval_positive CHECK (repeat_interval IS NULL OR repeat_interval > 0),
                    CONSTRAINT check_status_valid CHECK (status IN ('active', 'paused'))
                )
            """)
            print("subscriptions table is ready")

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)
            """)
            print("subscriptions index is ready")

            # provider_fees
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_fees (
                    provider VARCHAR PRIMARY KEY,
                    buy_fee DECIMAL NOT NULL,
                    sell_fee DECIMAL NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            print("provider_fees table is ready")

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
        volume: Decimal | None = None,
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


# ─── Fee helpers ────────────────────────────────────────────

async def get_fee(provider: str) -> tuple[Decimal, Decimal]:
    """
    Retrieve buy and sell fee rates for a provider.
    Returns (buy_fee, sell_fee) as Decimals.
    Raises ValueError if provider not found.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ProviderFee).where(ProviderFee.provider == provider)
        )
        fee_row = result.scalar_one_or_none()
        if fee_row is None:
            raise ValueError(f"Fee not found for provider: {provider}")
        fee = cast(ProviderFee, fee_row)
        return fee.buy_fee, fee.sell_fee

async def close_db():
    await engine.dispose()