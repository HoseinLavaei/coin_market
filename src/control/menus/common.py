"""
Common utilities for menu handlers.
Includes generic numeric keypad handler.
"""

from decimal import Decimal
from typing import cast

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from .menus import build_numeric_keyboard

# ─── Conversation States ─────────────────────────────────────
SELECT_PROVIDER, SELECT_TYPE, SELECT_VOLUME, SELECT_REPEAT, CONFIRM = range(5)


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


# ─── Numeric Keypad Helpers ────────────────────────────────

async def _update_numeric_display(
        query,
        num_buffer: str,
        num_field: str,
        include_negative: bool = False,
        allow_decimal: bool = False,
) -> None:
    """Update the numeric keypad display."""
    display = num_buffer if num_buffer else " "
    text = f"✏️ Enter {num_field} (number):\n\n{display}\n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(
            include_negative=include_negative,
            allow_decimal=allow_decimal,
        ),
        parse_mode=None,
    )


async def _handle_numeric_backspace(user_data: dict, num_buffer: str, state: int) -> int:
    num_buffer = num_buffer[:-1]
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_dot(user_data: dict, num_buffer: str, state: int) -> int:
    if "." not in num_buffer:
        num_buffer += "."
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_negative(user_data: dict, num_buffer: str, state: int) -> int:
    if num_buffer == "":
        num_buffer = "-"
    elif num_buffer.startswith("-"):
        num_buffer = num_buffer[1:]
    else:
        num_buffer = "-" + num_buffer
    user_data["num_buffer"] = num_buffer
    return state


async def _handle_numeric_digit(user_data: dict, num_buffer: str, digit: str, state: int) -> int:
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
    """Handle confirm (Next) key on numeric keypad."""
    if not num_buffer or num_buffer in ("-", "."):
        await safe_edit(query, "❌ Please enter a number.")
        return state

    try:
        if num_field == "volume":
            value = Decimal(num_buffer)
            if value <= 0:
                raise ValueError
        elif num_field == "repeat":
            value = int(num_buffer)
            if value <= 0:
                raise ValueError
        else:
            await safe_edit(query, "❌ Unknown field.")
            return state

        draft = get_draft(context)
        if num_field == "volume":
            draft["volume"] = value
        elif num_field == "repeat":
            draft["repeat_interval"] = value
        else:
            await safe_edit(query, "❌ Unknown field.")
            return state

        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)

        await safe_edit(
            query,
            f"✅ {num_field.capitalize()} set to: {num_buffer}",
        )
        return ConversationHandler.END

    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid number. Please try again.")
        return state


async def _handle_numeric_back(_context: ContextTypes.DEFAULT_TYPE, user_data: dict) -> int:
    user_data.pop("num_buffer", None)
    user_data.pop("num_field", None)
    return ConversationHandler.END


# ─── Main Numeric Input Handler ─────────────────────────────

async def handle_numeric_input(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        field: str,
        state: int,
        include_negative: bool = False,
        allow_decimal: bool = False,
) -> int:
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
    elif action == "negative":
        result = await _handle_numeric_negative(user_data, num_buffer, state)
    elif action == "next":
        result = await _handle_numeric_confirm(query, context, user_data, num_buffer, num_field, state)
    elif action == "back":
        result = await _handle_numeric_back(context, user_data)
    elif action.isdigit():
        result = await _handle_numeric_digit(user_data, num_buffer, action, state)
    else:
        return state

    # ─── Update display if we're still in the numeric state ──
    if result == state:
        updated_buffer = user_data.get("num_buffer", "")
        await _update_numeric_display(
            query,
            updated_buffer,
            num_field,
            include_negative,
            allow_decimal,
        )

    return result
