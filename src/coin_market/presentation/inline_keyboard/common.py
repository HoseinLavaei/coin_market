"""
Common utilities for menu handlers.
"""

from typing import cast
from decimal import Decimal
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from .menus import build_numeric_keyboard

# ─── Conversation States ─────────────────────────────────────
SELECT_PROVIDER, SELECT_TYPE, SELECT_VOLUME, SELECT_REPEAT, SELECT_CHAT, CONFIRM, SELECT_EDIT_SUB = range(7)


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

async def _update_numeric_display(
    query,
    num_buffer: str,
    num_field: str,
    include_negative: bool = False,
) -> None:
    """Update the numeric keypad display."""
    display = num_buffer if num_buffer else " "
    text = f"✏️ Enter {num_field} (number):\n\n{display}\n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(
            include_negative=include_negative,
            allow_decimal=(num_field == "volume"),
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


# ─── Parse value based on field ────────────────────────────

def _parse_field_value(num_field: str, num_buffer: str) -> tuple[bool, object, str | None]:
    """Parse the numeric input based on the field type."""
    match num_field:
        case "volume":
            try:
                value = Decimal(num_buffer)
                if value <= 0:
                    return False, None, "Volume must be positive."
                return True, value, None
            except ValueError:
                return False, None, "Invalid number."

        case "repeat":
            try:
                value = int(num_buffer)
                if value <= 0:
                    return False, None, "Interval must be positive."
                return True, value, None
            except ValueError:
                return False, None, "Invalid number."

        case "chat_id":
            try:
                value = int(num_buffer)
                return True, value, None
            except ValueError:
                return False, None, "Invalid number."

        case _:
            return False, None, "Unknown field."


def _set_draft_value(context: ContextTypes.DEFAULT_TYPE, num_field: str, value) -> str | None:
    """Update the draft with the parsed value. Returns error message or None."""
    draft = get_draft(context)

    match num_field:
        case "volume":
            draft["volume"] = value
        case "repeat":
            draft["repeat_interval"] = value
        case "chat_id":
            draft["chat_id"] = value
            draft["chat_method"] = "custom"
        case _:
            return "Unknown field."

    return None


# ─── Handle confirm ─────────────────────────────────────────

async def _handle_numeric_confirm(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user_data: dict,
    num_buffer: str,
    num_field: str,
    state: int,
) -> int:
    """Handle confirm (Next) key."""
    if not num_buffer or num_buffer in ("-", "."):
        await safe_edit(query, "❌ Please enter a number.")
        return state

    success, value, error = _parse_field_value(num_field, num_buffer)

    if not success:
        await safe_edit(query, f"❌ {error}")
        return state

    error = _set_draft_value(context, num_field, value)
    if error:
        await safe_edit(query, f"❌ {error}")
        return state

    user_data.pop("num_buffer", None)
    user_data.pop("num_field", None)

    await safe_edit(
        query,
        f"✅ {num_field.capitalize()} set to: {num_buffer}",
    )
    return ConversationHandler.END


async def _handle_numeric_back(
    context: ContextTypes.DEFAULT_TYPE,
    user_data: dict,
    num_field: str,
) -> int:
    user_data.pop("num_buffer", None)
    user_data.pop("num_field", None)

    if num_field == "chat_id":
        draft = get_draft(context)
        draft.pop("chat_method", None)

    return ConversationHandler.END


# ─── Main Numeric Input Handler ────────────────────────────

async def handle_numeric_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    field: str,
    state: int,
    include_negative: bool = False,
) -> int:
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

    match action:
        case "backspace":
            result = await _handle_numeric_backspace(user_data, num_buffer, state)
        case ".":
            result = await _handle_numeric_dot(user_data, num_buffer, state)
        case "negative":
            result = await _handle_numeric_negative(user_data, num_buffer, state)
        case "next":
            result = await _handle_numeric_confirm(query, context, user_data, num_buffer, num_field, state)
        case "back":
            result = await _handle_numeric_back(context, user_data, num_field)
        case _ if action.isdigit():
            result = await _handle_numeric_digit(user_data, num_buffer, action, state)
        case _:
            return state

    if result == state:
        updated_buffer = user_data.get("num_buffer", "")
        await _update_numeric_display(query, updated_buffer, num_field, include_negative)

    return result