"""
Volume selection handler.
Auto‑saves to DB immediately.
"""

from decimal import Decimal
from typing import Optional

from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler

from db.subscription_repository import save_subscription_settings
from .common import safe_edit, get_user_data, SELECT_VOLUME, get_current_subscription
from .menus import build_volume_keyboard, build_numeric_keyboard
from src.subscription_types import SubscriptionData


async def show_volume(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display volume selection menu with current selection shown."""
    sub = get_current_subscription(context)
    current: Optional[Decimal] = sub.volume if sub else None

    if current is not None:
        text = f"📦 Selected volume: {format(current, 'f')}\n\nSelect volume (or use Custom):"
    else:
        text = "📦 Select volume (or use Custom):"

    await safe_edit(query, text, reply_markup=build_volume_keyboard(current))
    return SELECT_VOLUME


async def _save_volume(context: ContextTypes.DEFAULT_TYPE, value: Optional[Decimal]) -> None:
    """Save volume to DB and update cached SubscriptionData."""
    user_data = get_user_data(context)
    user_id: Optional[int] = user_data.get("user_id")
    if not user_id:
        return

    await save_subscription_settings(user_id=user_id, volume=value)

    # Update cached SubscriptionData
    sub = get_current_subscription(context)
    if sub is not None:
        updated = SubscriptionData(
            id=sub.id,
            chat_id=sub.chat_id,
            provider=sub.provider,
            type_filter=sub.type_filter,
            volume=value,
            repeat_interval=sub.repeat_interval,
        )
        user_data["current_subscription"] = updated
    else:
        # Should not happen, but create minimal one
        user_data["current_subscription"] = SubscriptionData(
            id=0,
            chat_id=None,
            provider=None,
            type_filter=None,
            volume=value,
            repeat_interval=None,
        )


async def volume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle volume selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_VOLUME

    if not data.startswith("vol:"):
        return SELECT_VOLUME

    action = data.split(":", 1)[1]

    # ─── Custom ──────────────────────────────────────────────
    if action == "custom":
        user_data = get_user_data(context)
        user_data["num_field"] = "volume"
        user_data["num_buffer"] = ""
        text = "✏️ Enter volume (number):\n\n \n\n(use the keypad below)"
        await safe_edit(
            query,
            text,
            reply_markup=build_numeric_keyboard(include_negative=False, allow_decimal=True),
            parse_mode=None,
        )
        return SELECT_VOLUME

    # ─── Back ─────────────────────────────────────────────────
    if action == "back":
        from .selection_handlers import show_selection
        return await show_selection(query, context, "type")

    # ─── Next ─────────────────────────────────────────────────
    if action == "next":
        sub = get_current_subscription(context)
        if sub is None or sub.volume is None:
            await safe_edit(
                query,
                "❌ Please select a volume or use 'Custom'.",
                reply_markup=build_volume_keyboard(None),
            )
            return SELECT_VOLUME
        from .repeat_handler import show_repeat
        return await show_repeat(query, context)

    # ─── Menu ─────────────────────────────────────────────────
    if action == "menu":
        from .control_menus import show_main_menu
        return await show_main_menu(query, context)

    # ─── Preset value ─────────────────────────────────────────
    try:
        value = Decimal(action)
        await _save_volume(context, value)

        await safe_edit(
            query,
            f"📦 Selected volume: {value}\n\nSelect volume (or use Custom):",
            reply_markup=build_volume_keyboard(value),
        )
        return SELECT_VOLUME
    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid volume.")
        return SELECT_VOLUME


async def numeric_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle numeric keypad input for volume."""
    from .common import handle_numeric_input
    return await handle_numeric_input(update, context, "volume", SELECT_VOLUME, allow_decimal=True)
