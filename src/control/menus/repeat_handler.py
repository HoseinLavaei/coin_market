"""
Repeat interval selection handler.
Auto‑saves to DB immediately.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import (
    safe_edit,
    get_user_data,
    handle_numeric_input,
    SELECT_REPEAT,
)
from .menus import build_repeat_keyboard, build_numeric_keyboard
from ...db.repositories.subscription_repository import save_subscription_settings


async def show_repeat(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display repeat interval selection menu with current selection shown."""
    user_data = get_user_data(context)
    sub = user_data.get("current_subscription", {})
    current = sub.get("repeat_interval")
    is_new = user_data.get("is_new", False)

    # Ensure current is int | None (not Any)
    if not isinstance(current, int):
        current = None

    if current is not None:
        label = f"{current}m"
        text = f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):"
    else:
        text = "⏱️ Select interval (or use Custom):"

    await safe_edit(query, text, reply_markup=build_repeat_keyboard(current, show_next=is_new))
    return SELECT_REPEAT


async def _save_repeat(context: ContextTypes.DEFAULT_TYPE, value: int | None) -> None:
    """Save repeat interval to DB and update user_data."""
    user_data = get_user_data(context)
    user_id: int | None = user_data.get("user_id")
    if not user_id:
        return

    await save_subscription_settings(user_id=user_id, repeat_interval=value)

    sub = user_data.get("current_subscription", {})
    sub["repeat_interval"] = value
    user_data["current_subscription"] = sub


async def repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle repeat interval selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_REPEAT

    if not data.startswith("rep:"):
        return SELECT_REPEAT

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    is_new = user_data.get("is_new", False)

    # ─── Custom ──────────────────────────────────────────────
    if action == "custom":
        user_data["num_field"] = "repeat"
        user_data["num_buffer"] = ""
        text = "✏️ Enter interval in minutes (number):\n\n \n\n(use the keypad below)"
        await safe_edit(
            query,
            text,
            reply_markup=build_numeric_keyboard(include_negative=False, allow_decimal=False),
            parse_mode=None,
        )
        return SELECT_REPEAT

    # ─── Back ─────────────────────────────────────────────────
    if action == "back":
        from .volume_handler import show_volume
        return await show_volume(query, context)

    # ─── Next ─────────────────────────────────────────────────
    if action == "next":
        sub = user_data.get("current_subscription", {})
        current = sub.get("repeat_interval")
        if not isinstance(current, int):
            current = None

        if current is None:
            await safe_edit(
                query,
                "❌ Please select an interval or use 'Custom'.",
                reply_markup=build_repeat_keyboard(None, show_next=True),
            )
            return SELECT_REPEAT

        # New user – go to confirmation screen
        from .confirm_handler import show_confirm
        return await show_confirm(query, context)

    # ─── Menu ─────────────────────────────────────────────────
    if action == "menu":
        from .control_menus import show_main_menu
        return await show_main_menu(query, context)

    # ─── Preset value ─────────────────────────────────────────
    try:
        minutes = int(action)
        await _save_repeat(context, minutes)

        label = f"{minutes}m"
        await safe_edit(
            query,
            f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):",
            reply_markup=build_repeat_keyboard(minutes, show_next=is_new),
        )
        return SELECT_REPEAT
    except (ValueError, TypeError):
        await safe_edit(query, "❌ Invalid interval.")
        return SELECT_REPEAT


async def numeric_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle numeric keypad input for repeat interval."""
    return await handle_numeric_input(
        update,
        context,
        "repeat",
        SELECT_REPEAT,
        include_negative=False,
        allow_decimal=False,
    )
