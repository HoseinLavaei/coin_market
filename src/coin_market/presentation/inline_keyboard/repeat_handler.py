"""
Repeat interval selection handler.
Single‑select from presets or custom numeric input.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft, handle_numeric_input, get_user_data
from .menus import (
    build_repeat_keyboard,
    build_numeric_keyboard,
    SELECT_REPEAT,
)


async def show_repeat(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display repeat interval selection menu with current selection shown."""
    draft = get_draft(context)
    current: int | None = draft.get("repeat_interval")

    if current is not None:
        if current >= 60:
            label = f"{current // 60}m"
        else:
            label = f"{current}s"
        text = f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):"
    else:
        text = "⏱️ Select interval (or use Custom):"

    await safe_edit(query, text, reply_markup=build_repeat_keyboard(current))
    return SELECT_REPEAT


async def handle_repeat_preset(query, context: ContextTypes.DEFAULT_TYPE, value: str) -> int:
    """Handle preset interval selection."""
    draft = get_draft(context)
    try:
        interval = int(value)
        draft["repeat_interval"] = interval

        if interval >= 60:
            label = f"{interval // 60}m"
        else:
            label = f"{interval}s"

        await safe_edit(
            query,
            f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):",
            reply_markup=build_repeat_keyboard(interval),
        )
        return SELECT_REPEAT
    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid interval.")
        return SELECT_REPEAT


async def handle_repeat_custom(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom interval input."""
    user_data = get_user_data(context)
    user_data["num_field"] = "repeat"
    user_data["num_buffer"] = ""
    text = "✏️ Enter interval in seconds (number):\n\n \n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(),
        parse_mode=None,  # No Markdown
    )
    return SELECT_REPEAT


async def handle_repeat_next(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle next button for repeat selection."""
    draft = get_draft(context)
    if draft.get("repeat_interval") is None:
        await safe_edit(
            query,
            "❌ Please select an interval or use 'Custom'.",
            reply_markup=build_repeat_keyboard(None),
        )
        return SELECT_REPEAT
    # ─── Move to chat selection ──────────────────────
    from .chat_handler import show_chat
    return await show_chat(query, context)


async def handle_repeat_back(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button to return to volume selection."""
    from .volume_handler import show_volume
    return await show_volume(query, context)


async def repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle repeat interval selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_REPEAT

    if data.startswith("rep:"):
        action = data.split(":", 1)[1]

        if action == "custom":
            return await handle_repeat_custom(query, context)
        if action == "next":
            return await handle_repeat_next(query, context)
        if action == "back":
            return await handle_repeat_back(query, context)

        return await handle_repeat_preset(query, context, action)

    if data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    return SELECT_REPEAT


async def numeric_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle numeric keypad input for repeat interval."""
    return await handle_numeric_input(update, context, "repeat", SELECT_REPEAT)
