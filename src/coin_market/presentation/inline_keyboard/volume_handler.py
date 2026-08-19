"""
Volume selection handler.
Single‑select from presets or custom numeric input.
"""

from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft, handle_numeric_input, get_user_data
from .menus import (
    build_volume_keyboard,
    build_numeric_keyboard,
    SELECT_VOLUME,
)


async def show_volume(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display volume selection menu with current selection shown."""
    draft = get_draft(context)
    current = draft.get("volume")
    if current is not None:
        text = f"📦 Selected volume: {current}\n\nSelect volume (or use Custom):"
    else:
        text = "📦 Select volume (or use Custom):"
    await safe_edit(query, text, reply_markup=build_volume_keyboard(current))
    return SELECT_VOLUME


async def handle_volume_custom(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom volume input."""
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


async def handle_volume_next(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle next button for volume selection."""
    draft = get_draft(context)
    if draft.get("volume") is None:
        await safe_edit(
            query,
            "❌ Please select a volume or use 'Custom'.",
            reply_markup=build_volume_keyboard(None),
        )
        return SELECT_VOLUME
    from .repeat_handler import show_repeat
    return await show_repeat(query, context)


async def handle_volume_back(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button to return to type selection."""
    from .selection_handlers import show_selection
    return await show_selection(query, context, "type")


async def handle_volume_preset(query, context: ContextTypes.DEFAULT_TYPE, value: str) -> int:
    """Handle preset volume selection."""
    draft = get_draft(context)
    try:
        volume = Decimal(value)
        draft["volume"] = volume
        await safe_edit(
            query,
            f"📦 Selected volume: {volume}\n\nSelect volume (or use Custom):",
            reply_markup=build_volume_keyboard(volume),
        )
        return SELECT_VOLUME
    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid volume.")
        return SELECT_VOLUME


async def volume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle volume selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_VOLUME

    if data.startswith("vol:"):
        action = data.split(":", 1)[1]

        if action == "custom":
            return await handle_volume_custom(query, context)
        if action == "next":
            return await handle_volume_next(query, context)
        if action == "back":
            return await handle_volume_back(query, context)

        return await handle_volume_preset(query, context, action)

    if data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    return SELECT_VOLUME


async def numeric_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle numeric keypad input for volume."""
    return await handle_numeric_input(update, context, "volume", SELECT_VOLUME)
