"""
Confirm selection handler.
Shows a summary of all selections and allows confirmation.
- If user has existing subscription: updates it directly (no key).
- If user has no subscription: generates a key + pending subscription.
"""

import secrets
import traceback
from datetime import datetime, timedelta
from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft, CONFIRM
from .menus import build_confirm_keyboard
from .repeat_handler import show_repeat
from ...coins import build_subscription_description
from ...db import (
    get_subscription_for_user,
    add_or_replace_subscription,
    create_pending_subscription,
)
from ...environment import KEY_EXPIRY_SECONDS, TIMEZONE, BROADCAST_BOT_USERNAME


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


# ─── Helper handlers ──────────────────────────────────────────

async def _handle_cancel(query, context) -> int:
    clear_draft(context)
    await safe_edit(query, "❌ Subscription cancelled.")
    return ConversationHandler.END


async def _handle_back(query, context) -> int:
    return await show_repeat(query, context)


async def _handle_update_existing(
        query,
        context,
        user_id: int,
        provider_str: str | None,
        type_str: str | None,
        volume: Decimal | None,
        repeat_interval: int,
) -> int:
    existing = await get_subscription_for_user(user_id)
    if existing is None:
        return await _handle_new_subscription(query, context, user_id, provider_str, type_str, volume, repeat_interval)

    try:
        await add_or_replace_subscription(
            user_id=user_id,
            chat_id=existing.chat_id,
            provider=provider_str,
            type_filter=type_str,
            volume=volume,
            repeat_interval=repeat_interval,
        )
        clear_draft(context)
        await safe_edit(query,
                        "✅ Subscription updated successfully! The first update will be sent within the next minute.")
        return ConversationHandler.END
    except Exception as e:
        traceback.print_exc()
        await safe_edit(query, f"❌ Failed to update subscription: {e}")
        return ConversationHandler.END


async def _handle_new_subscription(
        query,
        context,
        user_id: int,
        provider_str: str | None,
        type_str: str | None,
        volume: Decimal | None,
        repeat_interval: int,
) -> int:
    key = str(secrets.randbelow(1000000)).zfill(6)
    expires_at: int = int((datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)).timestamp())

    try:
        await create_pending_subscription(
            key=key,
            user_id=user_id,
            provider=provider_str,
            type_filter=type_str,
            volume=volume,
            repeat_interval=repeat_interval,
            expires_at=expires_at,
        )
    except Exception as e:
        traceback.print_exc()
        await safe_edit(query, f"❌ Failed to create pending subscription: {e}")
        return ConversationHandler.END

    filter_desc = build_subscription_description(provider_str, type_str, volume, repeat_interval)
    link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={key}"

    await safe_edit(
        query,
        f"✅ Subscription request created!\n\n"
        f"Filters: {filter_desc}\n"
        f"Repeat every: {repeat_interval} minute(s)\n\n"
        f"To activate, click this link:\n"
        f"👉 {link}\n\n"
        f"Or open the Broadcast Bot with /start or /menu and enter the key manually:\n"
        f"🔑 {key}\n\n"
        f"(The key is valid for {KEY_EXPIRY_SECONDS} seconds.)",
        parse_mode=None,
    )
    clear_draft(context)
    return ConversationHandler.END


# ─── Main callback ────────────────────────────────────────────

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM

    if not data.startswith("confirm:"):
        return CONFIRM

    action = data.split(":", 1)[1]
    draft = get_draft(context)
    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    if action == "cancel":
        return await _handle_cancel(query, context)

    if action == "back":
        return await _handle_back(query, context)

    if action == "next":
        provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
        type_str = ",".join(draft.get("types", [])) if draft.get("types") else None
        repeat_interval = draft.get("repeat_interval")
        volume = draft.get("volume")

        if not isinstance(repeat_interval, int):
            await safe_edit(query, "❌ Invalid interval.")
            return ConversationHandler.END

        return await _handle_update_existing(
            query,
            context,
            user.id,
            provider_str,
            type_str,
            volume,
            repeat_interval,
        )

    return CONFIRM
