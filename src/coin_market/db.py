import urllib.parse
from datetime import datetime
from decimal import Decimal

import asyncpg
import sqlalchemy as sa
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .environment import DATABASE_URL


# ─── SQLAlchemy relational models ──────────────────────────

class Coin(Base):
    __tablename__ = "coin"

    coin_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    _buy_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    _sell_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    buy_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    sell_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)


class Order(Base):
    __tablename__ = "order"

    order_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("coin.coin_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)


class OrderBook(Base):
    __tablename__ = "orderbook"

    orderbook_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    asks_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)
    bids_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class Coins(Base):
    __tablename__ = "coins"

    coins_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    coin_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class OrderBooks(Base):
    __tablename__ = "orderbooks"

    orderbooks_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    orderbook_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class PendingSubscription(Base):
    __tablename__ = "pending_subscriptions"

    key: Mapped[str] = mapped_column(sa.String, primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(sa.String, default="pending")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'claimed', 'expired')", name="check_pending_status_valid"),
    )


# ─── Engine and session ─────────────────────────────────────

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─── init_db ──────────────────────────────────────────────────

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
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
            print("TimescaleDB extension is ready.")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS coin
                               (
                                   coin_id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   provider
                                   VARCHAR
                                   NOT
                                   NULL,
                                   base
                                   VARCHAR
                                   NOT
                                   NULL,
                                   quote
                                   VARCHAR
                                   NOT
                                   NULL,
                                   _buy_price
                                   DECIMAL
                                   NOT
                                   NULL,
                                   _sell_price
                                   DECIMAL
                                   NOT
                                   NULL,
                                   buy_fee
                                   DECIMAL
                                   NOT
                                   NULL,
                                   sell_fee
                                   DECIMAL
                                   NOT
                                   NULL,
                                   timestamp
                                   TIMESTAMPTZ
                                   NOT
                                   NULL
                               )
                               """)
            print("coin table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS "order"
                               (
                                   order_id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   coin_id
                                   INTEGER
                                   REFERENCES
                                   coin
                               (
                                   coin_id
                               ) NOT NULL,
                                   quantity DECIMAL NOT NULL
                                   )
                               """)
            print("order table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS orderbook
                               (
                                   orderbook_id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   asks_ids
                                   INTEGER [],
                                   bids_ids
                                   INTEGER
                               []
                               )
                               """)
            print("orderbook table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS coins
                               (
                                   coins_id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   provider
                                   VARCHAR
                                   NOT
                                   NULL,
                                   base
                                   VARCHAR
                                   NOT
                                   NULL,
                                   quote
                                   VARCHAR
                                   NOT
                                   NULL,
                                   coin_ids
                                   INTEGER
                               []
                               )
                               """)
            print("coins table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS orderbooks
                               (
                                   orderbooks_id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   provider
                                   VARCHAR
                                   NOT
                                   NULL,
                                   base
                                   VARCHAR
                                   NOT
                                   NULL,
                                   quote
                                   VARCHAR
                                   NOT
                                   NULL,
                                   orderbook_ids
                                   INTEGER
                               []
                               )
                               """)
            print("orderbooks table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS pending_subscriptions
                               (
                                   key
                                   TEXT
                                   PRIMARY
                                   KEY,
                                   user_id
                                   BIGINT
                                   NOT
                                   NULL,
                                   provider
                                   VARCHAR,
                                   type_filter
                                   VARCHAR,
                                   volume
                                   DECIMAL,
                                   repeat_interval
                                   INT,
                                   chat_id
                                   BIGINT,
                                   status
                                   VARCHAR
                                   DEFAULT
                                   'pending',
                                   created_at
                                   TIMESTAMPTZ
                                   DEFAULT
                                   NOW
                               (
                               ),
                                   expires_at TIMESTAMPTZ NOT NULL,
                                   CONSTRAINT check_pending_status_valid CHECK
                               (
                                   status
                                   IN
                               (
                                   'pending',
                                   'claimed',
                                   'expired'
                               ))
                                   )
                               """)
            print("pending_subscriptions table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS subscriptions
                               (
                                   id
                                   SERIAL
                                   PRIMARY
                                   KEY,
                                   chat_id
                                   BIGINT
                                   NOT
                                   NULL,
                                   user_id
                                   BIGINT
                                   NOT
                                   NULL,
                                   provider
                                   VARCHAR,
                                   type_filter
                                   VARCHAR,
                                   volume
                                   DECIMAL,
                                   repeat_interval
                                   INT,
                                   status
                                   VARCHAR
                                   DEFAULT
                                   'active',
                                   created_at
                                   TIMESTAMPTZ
                                   DEFAULT
                                   NOW
                               (
                               ),
                                   updated_at TIMESTAMPTZ DEFAULT NOW
                               (
                               ),
                                   CONSTRAINT check_repeat_interval_positive CHECK
                               (
                                   repeat_interval
                                   IS
                                   NULL
                                   OR
                                   repeat_interval >
                                   0
                               ),
                                   CONSTRAINT check_status_valid CHECK
                               (
                                   status
                                   IN
                               (
                                   'active',
                                   'paused'
                               ))
                                   )
                               """)
            print("subscriptions table ready")

            await conn.execute("""
                               CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)
                               """)
            print("subscriptions index ready")

            await conn.execute("""
                               CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions (user_id)
                               """)
            print("subscriptions user_id index ready")

        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


async def close_db():
    await engine.dispose()
