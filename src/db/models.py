"""
SQLAlchemy ORM models – only subscriptions and pending_subscriptions.
"""

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base = declarative_base()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, unique=True, index=True)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int] = mapped_column(sa.Integer, nullable=False)  # in minutes
    last_sent_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)  # minutes since epoch
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        CheckConstraint("repeat_interval > 0", name="check_repeat_interval_positive"),
    )


class PendingSubscription(Base):
    __tablename__ = "pending_subscriptions"

    key: Mapped[str] = mapped_column(sa.String, primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(sa.String, default="pending")
    expires_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)  # seconds since epoch

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'claimed', 'expired')", name="check_pending_status_valid"),
    )
