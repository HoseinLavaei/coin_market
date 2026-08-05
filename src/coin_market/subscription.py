from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def build_subscription_description(
        provider: str | None,
        type_filter: str | None,
        volume: float | None,
        repeat_interval: int | None,
) -> str:
    """Build a human-readable description of subscription filters."""
    parts = []
    if provider:
        parts.append(f"provider={provider}")
    if type_filter:
        parts.append(f"type={type_filter}")
    if volume is not None:
        parts.append(f"volume={volume}")
    if repeat_interval is not None:
        parts.append(f"repeat={repeat_interval}s")
    return " + ".join(parts) if parts else "all data"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)  # 'OTC' or 'P2P'
    volume: Mapped[float | None] = mapped_column(sa.Numeric, nullable=True)
    repeat_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[str] = mapped_column(sa.String, default="active")  # 'active' or 'paused'
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:
        desc = build_subscription_description(
            self.provider,
            self.type_filter,
            self.volume,
            self.repeat_interval,
        )
        return f"Subscription(id={self.id}, chat_id={self.chat_id}, {desc}, status={self.status})"