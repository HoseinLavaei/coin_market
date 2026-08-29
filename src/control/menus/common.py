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
MAIN_MENU, SELECT_PROVIDER, SELECT_TYPE, SELECT_VOLUME, SELECT_REPEAT, CONFIRM = range(6)


# ─── User Data helpers ──────────────────────────────────────

def get_user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Return user_data as a typed dict."""
    return cast(dict, context.user_data)


def get_current_subscription(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Get the current subscription from user_data (loaded from DB)."""
    user_data = get_user_data(context)
    return user_data.get("current_subscription")


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


async def _save_numeric_value(
        user_id: int,
        num_field: str,
        value: Decimal | int,
        user_data: dict,
) -> None:
    """Save the numeric value to the database and update user_data."""
    from ...db.repositories.subscription_repository import save_subscription_settings

    if num_field == "volume":
        # mypy can't infer that value is Decimal here, but we know it
        await save_subscription_settings(user_id=user_id, volume=value)  # type: ignore[arg-type]
        if user_data.get("current_subscription"):
            user_data["current_subscription"]["volume"] = value
    elif num_field == "repeat":
        await save_subscription_settings(user_id=user_id, repeat_interval=value)  # type: ignore[arg-type]
        if user_data.get("current_subscription"):
            user_data["current_subscription"]["repeat_interval"] = value


def _validate_and_parse_numeric(num_buffer: str, num_field: str) -> Decimal | int | None:
    """Parse and validate numeric input for volume or repeat."""
    try:
        if num_field == "volume":
            val = Decimal(num_buffer)
            if val <= 0:
                return None
            return val
        elif num_field == "repeat":
            val = int(num_buffer)
            if val <= 0:
                return None
            return val
        else:
            return None
    except (ValueError, TypeError):
        return None


async def _handle_numeric_confirm(
        query,
        context: ContextTypes.DEFAULT_TYPE,
        user_data: dict,
        num_buffer: str,
        num_field: str,
        state: int,
) -> int:
    """Handle confirm (Set) key on numeric keypad."""
    if not num_buffer or num_buffer in ("-", "."):
        await safe_edit(query, "❌ Please enter a number.")
        return state

    parsed = _validate_and_parse_numeric(num_buffer, num_field)
    if parsed is None:
        await safe_edit(query, "❌ Invalid number. Please try again.")
        return state

    user_id = user_data.get("user_id")
    if not isinstance(user_id, int):
        await safe_edit(query, "❌ Could not identify user.")
        return state

    await _save_numeric_value(user_id, num_field, parsed, user_data)

    # Clear numeric state
    user_data.pop("num_buffer", None)
    user_data.pop("num_field", None)

    # Return to the appropriate sub‑menu
    if num_field == "volume":
        from .volume_handler import show_volume
        return await show_volume(query, context)
    else:
        from .repeat_handler import show_repeat
        return await show_repeat(query, context)


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
        return result  # Don't try to update display again
    elif action == "back":
        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)
        if num_field == "volume":
            from .volume_handler import show_volume
            return await show_volume(query, context)
        else:
            from .repeat_handler import show_repeat
            return await show_repeat(query, context)
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
