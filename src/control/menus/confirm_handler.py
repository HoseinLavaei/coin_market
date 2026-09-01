"""
Confirmation handler for new users.
Shows summary and confirms before generating activation key.
"""

import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler

from src import logger
from .common import safe_edit, get_user_data, CONFIRM, get_current_subscription
from .menus import build_confirm_keyboard, build_activation_keyboard
from .repeat_handler import show_repeat
from ...db import create_or_replace_pending
from ...environment import KEY_EXPIRY_SECONDS, TIMEZONE, BROADCAST_BOT_USERNAME
from src.subscription_types import SubscriptionData


def build_subscription_description(
        provider: Optional[str],
        type_filter: Optional[str],
        volume: Optional[Decimal],
        repeat_interval: Optional[int],
) -> str:
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
        parts.append(f"📦 volume={format(volume, 'f')}")
    if repeat_interval is not None:
        parts.append(f"⏱️ repeat={repeat_interval}m")

    return " + ".join(parts) if parts else "📊 all data"


async def show_confirm(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display confirmation menu with subscription summary."""
    sub = get_current_subscription(context)
    if sub is None:
        await safe_edit(query, "❌ No subscription data found.")
        return ConversationHandler.END

    summary = build_subscription_description(
        sub.provider,
        sub.type_filter,
        sub.volume,
        sub.repeat_interval,
    )

    text = (
        "<b>📋 Confirm Subscription</b>\n\n"
        f"{summary}\n\n"
        "Press Confirm to activate your subscription:"
    )

    await safe_edit(query, text, reply_markup=build_confirm_keyboard(), parse_mode="HTML")
    return CONFIRM


async def perform_activation(
        query: CallbackQuery,
        user_id: int,
        sub: SubscriptionData,
) -> int:
    """
    Generate a key and show an activation button that opens the URL.
    Called when the user presses Confirm.
    """
    key = str(secrets.randbelow(1000000)).zfill(6)
    expires_at: int = int((datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)).timestamp())

    try:
        await create_or_replace_pending(
            user_id=user_id,
            provider=sub.provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            repeat_interval=sub.repeat_interval,
            key=key,
            expires_at=expires_at,
        )
    except Exception as e:
        logger.error(f"Failed to create pending subscription: {e}")
        await safe_edit(query, f"❌ Failed to create pending subscription: {e}")
        return ConversationHandler.END

    filter_desc = build_subscription_description(
        sub.provider,
        sub.type_filter,
        sub.volume,
        sub.repeat_interval,
    )
    link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={key}"

    await safe_edit(
        query,
        f"✅ Subscription request created!\n\n"
        f"Filters: {filter_desc}\n"
        f"Repeat every: {sub.repeat_interval} minute(s)\n\n"
        f"Click the button below to activate (key: {key}, valid for {KEY_EXPIRY_SECONDS}s):",
        reply_markup=build_activation_keyboard(link),
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
    if not data:
        return CONFIRM

    if data == "activation:cancel":
        await safe_edit(query, "❌ Activation cancelled.")
        return ConversationHandler.END

    if not data.startswith("confirm:"):
        return CONFIRM

    action = data.split(":", 1)[1]

    if action == "back":
        return await show_repeat(query, context)

    if action == "confirm":
        user_data = get_user_data(context)
        user_id = user_data.get("user_id")
        sub = get_current_subscription(context)

        if not isinstance(user_id, int) or sub is None:
            await safe_edit(query, "❌ Could not identify user or subscription.")
            return ConversationHandler.END

        return await perform_activation(query, user_id, sub)

    return CONFIRM
