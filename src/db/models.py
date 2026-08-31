"""
SQLAlchemy ORM models – only one table: subscriptions.
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
    user_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True, unique=True, index=True)  # NULL for channel/group subscriptions (manual)
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True, index=True)  # NULL = pending
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=False)  # minutes
    last_sent_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)  # minutes since epoch
    activation_key: Mapped[str | None] = mapped_column(sa.String, nullable=True, unique=True)
    expires_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        CheckConstraint("repeat_interval > 0", name="check_repeat_interval_positive"),
    )
