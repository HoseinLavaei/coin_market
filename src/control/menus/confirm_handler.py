"""
Confirm selection handler.
Shows a summary of all selections and confirms.
- If user has an active subscription (chat_id NOT NULL): updates it directly.
- Otherwise: generates a key + pending subscription.
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
from ...db import (
    get_active_subscription_for_user,
    update_active_subscription,
    create_or_replace_pending,
)
from ...environment import KEY_EXPIRY_SECONDS, TIMEZONE, BROADCAST_BOT_USERNAME


def build_subscription_description(provider, type_filter, volume, repeat_interval) -> str:

    parts = []
    if provider:
        if "," in provider:
            provider_names = provider.split(",")
            parts.append(f"🏛️ providers={', '.join(provider_names)}")
        else:
            parts.append(f"🏛️ provider={provider}")

    if type_filter:
        if "," in type_filter:
            type_names = type_filter.split(",")
            parts.append(f"📊 types={', '.join(type_names)}")
        else:
            parts.append(f"📊 type={type_filter}")

    if volume is not None:
        parts.append(f"📦 volume={volume}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}m")

    return " + ".join(parts) if parts else "📊 all data"


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
    # Cancel: return to main menu without applying
    from .control_menus import show_main_menu
    await safe_edit(query, "Returning to main menu.")
    return await show_main_menu(query, context)


async def _handle_back(query, context) -> int:
    return await show_repeat(query, context)


async def _handle_existing_active(
        query,
        context,
        user_id: int,
        provider_str: str | None,
        type_str: str | None,
        volume: Decimal | None,
        repeat_interval: int,
) -> int:
    """Update an existing active subscription directly."""
    try:
        await update_active_subscription(
            user_id=user_id,
            provider=provider_str,
            type_filter=type_str,
            volume=volume,
            repeat_interval=repeat_interval,
        )
        clear_draft(context)
        await safe_edit(query, "✅ Subscription updated successfully! The first update will be sent within the next minute.")
        return ConversationHandler.END
    except Exception as e:
        traceback.print_exc()
        await safe_edit(query, f"❌ Failed to update subscription: {e}")
        return ConversationHandler.END


async def _create_and_show_pending(
        query,
        context,
        user_id: int,
        provider_str: str | None,
        type_str: str | None,
        volume: Decimal | None,
        repeat_interval: int,
) -> int:
    """Generate a key, create/replace pending subscription, and show activation link."""
    key = str(secrets.randbelow(1000000)).zfill(6)
    expires_at: int = int((datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)).timestamp())

    try:
        await create_or_replace_pending(
            user_id=user_id,
            provider=provider_str,
            type_filter=type_str,
            volume=volume,
            repeat_interval=repeat_interval,
            key=key,
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


async def _handle_confirm(query, context, user_id: int, draft: dict) -> int:
    """
    Handle the 'Done' action from the confirmation menu.
    Checks if the user has an active subscription and routes accordingly.
    """
    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None
    repeat_interval = draft.get("repeat_interval")
    volume = draft.get("volume")

    if not isinstance(repeat_interval, int):
        await safe_edit(query, "❌ Invalid interval.")
        return ConversationHandler.END

    existing_active = await get_active_subscription_for_user(user_id)

    if existing_active:
        return await _handle_existing_active(
            query,
            context,
            user_id,
            provider_str,
            type_str,
            volume,
            repeat_interval,
        )
    else:
        return await _create_and_show_pending(
            query,
            context,
            user_id,
            provider_str,
            type_str,
            volume,
            repeat_interval,
        )


# ─── Main callback ────────────────────────────────────────────

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    data = query.data
    if not data or not data.startswith("confirm:"):
        return CONFIRM

    action = data.split(":", 1)[1]

    if action == "cancel":
        return await _handle_cancel(query, context)

    if action == "back":
        return await _handle_back(query, context)

    if action == "done":
        user = update.effective_user
        if not user:
            await safe_edit(query, "❌ Could not identify user.")
            return ConversationHandler.END
        draft = get_draft(context)
        return await _handle_confirm(query, context, user.id, draft)

    return CONFIRM