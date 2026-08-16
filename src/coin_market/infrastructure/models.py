"""
SQLAlchemy ORM models for all database tables.
Uses PostgreSQL-specific array types for storing IDs and foreign key relationships.
"""

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base = declarative_base()


class Coin(Base):
    """Individual market price entry (OTC or P2P) with raw prices and fees."""
    __tablename__ = "coin"

    coin_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    raw_buy_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    raw_sell_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    buy_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    sell_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)


class Order(Base):
    """Individual order within an order book (price coin + quantity)."""
    __tablename__ = "order"

    order_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("coin.coin_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)


class OrderBook(Base):
    """
    Container for asks and bids. Stores only the IDs of orders in arrays,
    allowing efficient retrieval of related order details.
    """
    __tablename__ = "orderbook"

    orderbook_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    asks_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)
    bids_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class Coins(Base):
    """
    Grouping of coin IDs by (provider, base, quote). Used for historical snapshots.
    """
    __tablename__ = "coins"

    coins_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    coin_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class OrderBooks(Base):
    """
    Grouping of order book IDs by (provider, base, quote). Used for historical snapshots.
    """
    __tablename__ = "orderbooks"

    orderbooks_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    orderbook_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class PendingSubscription(Base):
    """
    Temporary subscription request awaiting activation via a one‑time key.
    Expires after a defined period.
    """
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


class Subscription(Base):
    """
    Active or paused subscription for a specific chat. Contains filter criteria and update interval.
    """
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[str] = mapped_column(sa.String, default="active")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        CheckConstraint("repeat_interval IS NULL OR repeat_interval > 0", name="check_repeat_interval_positive"),
        CheckConstraint("status IN ('active', 'paused')", name="check_status_valid"),
    )
