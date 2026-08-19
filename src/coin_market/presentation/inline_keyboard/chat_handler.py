"""
Chat selection handler.
Choose between Custom Chat ID (numeric input) or Get Key.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft, handle_numeric_input, get_user_data
from .menus import (
    build_chat_keyboard,
    build_numeric_keyboard,
    SELECT_CHAT,
)


async def show_chat(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display chat selection menu with current selection shown."""
    draft = get_draft(context)
    chat_method = draft.get("chat_method")
    chat_id = draft.get("chat_id")

    if chat_method == "custom" and chat_id is not None:
        selected = "custom"
        text = f"📨 Selected: Custom Chat ID ({chat_id})\n\nChoose delivery method:"
    elif chat_method == "key":
        selected = "key"
        text = "📨 Selected: Get Key (activate later)\n\nChoose delivery method:"
    else:
        selected = None
        text = "📨 Choose delivery method:"

    await safe_edit(query, text, reply_markup=build_chat_keyboard(selected))
    return SELECT_CHAT


async def handle_chat_custom(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Custom Chat ID selection."""
    user_data = get_user_data(context)
    user_data["num_field"] = "chat_id"
    user_data["num_buffer"] = ""
    text = "✏️ Enter Chat ID (number):\n\n \n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(
            include_negative=True,
            allow_decimal=False,
        ),
        parse_mode=None,
    )
    return SELECT_CHAT


async def handle_chat_key(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Get Key selection."""
    draft = get_draft(context)
    draft["chat_method"] = "key"
    draft["chat_id"] = None

    await safe_edit(
        query,
        "📨 Selected: Get Key (activate later)\n\nChoose delivery method:",
        reply_markup=build_chat_keyboard("key"),
    )
    return SELECT_CHAT


async def handle_chat_next(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle next button for chat selection."""
    draft = get_draft(context)
    chat_method = draft.get("chat_method")

    if chat_method is None:
        await safe_edit(
            query,
            "❌ Please choose a delivery method.",
            reply_markup=build_chat_keyboard(None),
        )
        return SELECT_CHAT

    if chat_method == "custom" and draft.get("chat_id") is None:
        await safe_edit(
            query,
            "❌ Please enter a Chat ID using 'Custom Chat ID'.",
            reply_markup=build_chat_keyboard("custom"),
        )
        return SELECT_CHAT

    # ─── Move to confirm ─────────────────────────────────────
    from .confirm_handler import show_confirm
    return await show_confirm(query, context)


async def handle_chat_back(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button to return to repeat selection."""
    from .repeat_handler import show_repeat
    return await show_repeat(query, context)


async def chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle chat selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_CHAT

    if data.startswith("chat:"):
        action = data.split(":", 1)[1]

        if action == "custom":
            return await handle_chat_custom(query, context)
        if action == "key":
            return await handle_chat_key(query, context)
        if action == "next":
            return await handle_chat_next(query, context)
        if action == "back":
            return await handle_chat_back(query, context)

    if data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    return SELECT_CHAT


async def numeric_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle numeric keypad input for chat ID."""
    return await handle_numeric_input(
        update,
        context,
        "chat_id",
        SELECT_CHAT,
        include_negative=True,
    )
