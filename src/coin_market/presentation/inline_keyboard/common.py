"""
Common utilities for menu handlers.
"""

from decimal import Decimal
from typing import cast

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from .menus import build_numeric_keyboard


# ─── User Data & Draft Management ─────────────────────────

def get_user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Return user_data as a typed dict."""
    return cast(dict, context.user_data)


def get_draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Get or initialize the draft dictionary."""
    user_data = get_user_data(context)
    if "draft" not in user_data:
        user_data["draft"] = {
            "providers": [],
            "types": [],
            "volume": None,
            "repeat_interval": None,
            "chat_method": None,
            "chat_id": None,
        }
    return user_data["draft"]


def clear_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the draft from user_data."""
    user_data = get_user_data(context)
    user_data.pop("draft", None)


# ─── Safe Edit ─────────────────────────────────────────────

async def safe_edit(query, text: str, reply_markup=None, parse_mode=None) -> None:
    """Edit message, ignoring 'Message is not modified' errors."""
    if query is None:
        return
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            raise


async def safe_edit_markup(query, reply_markup) -> None:
    """Edit only the reply markup, ignoring 'Message is not modified' errors."""
    if query is None:
        return
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            raise


# ─── Numeric Keyboard Helpers ─────────────────────────────

async def _update_numeric_display(query, num_buffer: str, num_field: str) -> None:
    """Update the numeric keypad display."""
    display = num_buffer if num_buffer else " "
    text = f"✏️ Enter {num_field} (number):\n\n{display}\n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(),
        parse_mode=None,  # No Markdown to avoid entity parsing errors
    )


async def _handle_numeric_backspace(user_data: dict, num_buffer: str, state: int) -> int:
    """Handle backspace key."""
    num_buffer = num_buffer[:-1]
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_dot(user_data: dict, num_buffer: str, state: int) -> int:
    """Handle dot key."""
    if "." not in num_buffer:
        num_buffer += "."
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_digit(user_data: dict, num_buffer: str, digit: str, state: int) -> int:
    """Handle digit key."""
    num_buffer += digit
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_confirm(
        query,
        context: ContextTypes.DEFAULT_TYPE,
        user_data: dict,
        num_buffer: str,
        num_field: str,
        state: int,
) -> int:
    """Handle confirm (Next) key."""
    if not num_buffer:
        await safe_edit(query, "❌ Please enter a number.")
        return state

    try:
        value = Decimal(num_buffer)
        if value <= 0:
            raise ValueError

        draft = get_draft(context)
        if num_field == "volume":
            draft["volume"] = value
        elif num_field == "repeat":
            draft["repeat_interval"] = int(value)
        elif num_field == "chat_id":
            draft["chat_id"] = int(value)
            draft["chat_method"] = "custom"
        else:
            await safe_edit(query, "❌ Unknown field.")
            return state

        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)

        await safe_edit(
            query,
            f"✅ {num_field.capitalize()} set to: {value}",
        )
        return ConversationHandler.END

    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid number. Please try again.")
        return state


async def _handle_numeric_back(
        context: ContextTypes.DEFAULT_TYPE,
        user_data: dict,
        num_field: str,
) -> int:
    """Handle back button to return to previous menu."""
    user_data.pop("num_buffer", None)
    user_data.pop("num_field", None)

    if num_field == "chat_id":
        draft = get_draft(context)
        draft.pop("chat_method", None)

    return ConversationHandler.END


# ─── Main Numeric Input Handler ────────────────────────────

async def handle_numeric_input(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, state: int) -> int:
    """
    Generic numeric keypad handler.
    Routes to specific helpers based on the action.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data or not data.startswith("num:"):
        return state

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    num_buffer = user_data.get("num_buffer", "")
    num_field = user_data.get("num_field", field)

    # ─── Route to specific handler ──────────────────────────
    if action == "backspace":
        result = await _handle_numeric_backspace(user_data, num_buffer, state)
    elif action == ".":
        result = await _handle_numeric_dot(user_data, num_buffer, state)
    elif action == "next":
        result = await _handle_numeric_confirm(query, context, user_data, num_buffer, num_field, state)
    elif action == "back":
        result = await _handle_numeric_back(context, user_data, num_field)
    elif action.isdigit():
        result = await _handle_numeric_digit(user_data, num_buffer, action, state)
    else:
        return state

    # ─── Update display if we're still in the numeric state ──
    if result == state:
        updated_buffer = user_data.get("num_buffer", "")
        await _update_numeric_display(query, updated_buffer, num_field)

    return result
