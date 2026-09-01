"""
Database package – connection, models, helpers, and repositories.
"""

# ─── Database connection ────────────────────────────────────
from .database import AsyncSessionLocal, close_db

# ─── Helpers ────────────────────────────────────────────────
from .helpers import now_minutes, now_seconds

# ─── Models ─────────────────────────────────────────────────
from .models import Subscription

# ─── Repositories ───────────────────────────────────────────
from .subscription_repository import (
    get_subscription_for_user,
    update_last_sent_at,
    delete_subscription,
    get_due_subscriptions_sync,
    update_last_sent_at_sync,
    get_active_subscription_for_user,
    get_pending_by_key,
    create_or_replace_pending,
    claim_subscription_by_key,
    update_active_subscription,
)
