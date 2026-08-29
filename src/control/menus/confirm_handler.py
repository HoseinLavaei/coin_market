"""
Confirmation handler for new users.
Shows summary and confirms before generating activation key.
"""

import secrets
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import logger
from .common import safe_edit, get_user_data, CONFIRM
from .menus import build_confirm_keyboard
from .repeat_handler import show_repeat
from ...db import create_or_replace_pending
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
    user_data = get_user_data(context)
    sub = user_data.get("current_subscription", {})

    provider = sub.get("provider")
    type_filter = sub.get("type_filter")
    volume = sub.get("volume")
    repeat_interval = sub.get("repeat_interval")

    summary = build_subscription_description(provider, type_filter, volume, repeat_interval)

    text = (
        "<b>📋 Confirm Subscription</b>\n\n"
        f"{summary}\n\n"
        "Press Confirm to activate your subscription:"
    )

    await safe_edit(query, text, reply_markup=build_confirm_keyboard(), parse_mode="HTML")
    return CONFIRM


async def perform_activation(query, user_id: int, sub: dict) -> int:
    """
    Generate a key and activate the pending subscription.
    Called when the user presses Confirm.
    """
    key = str(secrets.randbelow(1000000)).zfill(6)
    expires_at: int = int((datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)).timestamp())

    provider = sub.get("provider")
    type_filter = sub.get("type_filter")
    volume = sub.get("volume")
    repeat_interval = sub.get("repeat_interval", 1)

    try:
        await create_or_replace_pending(
            user_id=user_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            key=key,
            expires_at=expires_at,
        )
    except Exception as e:
        logger.error(f"Failed to create pending subscription: {e}")
        await safe_edit(query, f"❌ Failed to create pending subscription: {e}")
        return ConversationHandler.END

    filter_desc = build_subscription_description(provider, type_filter, volume, repeat_interval)
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
    return ConversationHandler.END


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

    if action == "back":
        return await show_repeat(query, context)

    if action == "confirm":
        user_data = get_user_data(context)
        user_id = user_data.get("user_id")
        sub = user_data.get("current_subscription")

        if not isinstance(user_id, int) or not isinstance(sub, dict):
            await safe_edit(query, "❌ Could not identify user.")
            return ConversationHandler.END

        return await perform_activation(query, user_id, sub)

    return CONFIRM
