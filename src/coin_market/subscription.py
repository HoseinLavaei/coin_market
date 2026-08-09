from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def build_subscription_description(
        provider: str | None,
        type_filter: str | None,
        volume: Decimal | None,
        repeat_interval: int | None,
) -> str:
    parts = []
    if provider:
        parts.append(f"🏛️ provider={provider}")
    if type_filter:
        if type_filter == "OTC":
            parts.append("💰 type=OTC")
        elif type_filter == "P2P":
            parts.append("🤝 type=P2P")
        else:
            parts.append(f"type={type_filter}")
    if volume is not None:
        parts.append(f"📦 volume={volume}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}s")
    return " + ".join(parts) if parts else "📊 all data"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)  # DECIMAL
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

    def __repr__(self) -> str:
        desc = build_subscription_description(
            self.provider,
            self.type_filter,
            self.volume,
            self.repeat_interval,
        )
        return f"Subscription(id={self.id}, chat_id={self.chat_id}, {desc}, status={self.status})"
