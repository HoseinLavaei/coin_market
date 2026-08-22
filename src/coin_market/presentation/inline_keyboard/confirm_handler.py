"""
Confirm selection handler.
Shows a summary of all selections and allows confirmation.
Only key‑based activation is supported (no custom chat ID).
"""

import secrets
import traceback
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft
from .menus import (
    build_confirm_keyboard,
    CONFIRM,
)
from ...domain.value_objects import build_subscription_description
from ...environment import KEY_EXPIRY_SECONDS, TIMEZONE, BROADCAST_BOT_USERNAME
from ...infrastructure.repositories import (
    create_pending_subscription,
    update_subscription_by_id,
)
from ...services.subscription_scheduler import reload_subscriptions_immediate


# ─── Show confirm screen ─────────────────────────────────────

async def show_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display confirmation menu with subscription summary."""
    draft = get_draft(context)

    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None

    summary = build_subscription_description(
        provider_str,
        type_str,
        draft.get("volume"),
        draft.get("repeat_interval"),
    )

    text = (
        "📋 **Confirm Subscription**\n\n"
        f"{summary}\n\n"
        "Review your selections and confirm:"
    )

    await safe_edit(query, text, reply_markup=build_confirm_keyboard())
    return CONFIRM


# ─── Handle editing ──────────────────────────────────────────

async def _handle_edit_subscription(query, context, user_id: int) -> int:
    """Handle updating an existing subscription."""
    draft = get_draft(context)
    edit_id = draft.get("edit_id")

    if not isinstance(edit_id, int):
        await safe_edit(query, "❌ Invalid subscription ID.")
        return ConversationHandler.END

    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None

    count = await update_subscription_by_id(
        sub_id=edit_id,
        user_id=user_id,
        provider=provider_str,
        type_filter=type_str,
        volume=draft.get("volume"),
        repeat_interval=draft.get("repeat_interval"),
    )
    if count:
        await reload_subscriptions_immediate()
        await safe_edit(query, "✅ Subscription updated and reloaded.")
    else:
        await safe_edit(query, "❌ Failed to update subscription.")
    clear_draft(context)
    return ConversationHandler.END


# ─── Create new subscription (key only) ─────────────────────

async def _handle_new_subscription(query, context, user_id: int) -> int:
    """Create a key‑based pending subscription."""
    draft = get_draft(context)

    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None

    # ─── Generate 6-digit numeric key ───────────────────────
    key = str(secrets.randbelow(1000000)).zfill(6)
    expires_at = datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)

    try:
        await create_pending_subscription(
            key=key,
            user_id=user_id,
            provider=provider_str,
            type_filter=type_str,
            volume=draft.get("volume"),
            repeat_interval=draft.get("repeat_interval"),
            expires_at=expires_at,
        )
    except Exception as e:
        traceback.print_exc()
        await safe_edit(query, f"❌ Failed to create pending subscription: {e}")
        return ConversationHandler.END

    filter_desc = build_subscription_description(
        provider_str,
        type_str,
        draft.get("volume"),
        draft.get("repeat_interval"),
    )

    # ─── Build activation link ──────────────────────────────
    link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={key}"

    await safe_edit(
        query,
        f"✅ Subscription request created!\n\n"
        f"Filters: {filter_desc}\n"
        f"Repeat every: {draft['repeat_interval']}s\n\n"
        f"To activate, click this link:\n"
        f"👉 {link}\n\n"
        f"Or open the Broadcast Bot with /start or /menu and enter the key manually:\n"
        f"🔑 {key}\n\n"
        f"(The key is valid for {KEY_EXPIRY_SECONDS} seconds.)",
        parse_mode=None,
    )
    clear_draft(context)
    return ConversationHandler.END


# ─── Confirm callback handlers ──────────────────────────────

async def handle_confirm_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm (Next) – create or update the subscription."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    draft = get_draft(context)
    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    # ─── Check if we're editing ─────────────────────────────
    if draft.get("edit_id") is not None:
        return await _handle_edit_subscription(query, context, user.id)

    # ─── New subscription ────────────────────────────────────
    return await _handle_new_subscription(query, context, user.id)


async def handle_confirm_back(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button to return to repeat selection."""
    from .repeat_handler import show_repeat
    return await show_repeat(query, context)


async def handle_confirm_cancel(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancel button."""
    clear_draft(context)
    await safe_edit(query, "❌ Subscription cancelled.")
    return ConversationHandler.END


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM

    if data.startswith("confirm:"):
        action = data.split(":", 1)[1]

        if action == "next":
            return await handle_confirm_next(update, context)
        if action == "back":
            return await handle_confirm_back(query, context)
        if action == "cancel":
            return await handle_confirm_cancel(query, context)

    if data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    return CONFIRM