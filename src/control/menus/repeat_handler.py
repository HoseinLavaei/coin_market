"""
Repeat interval selection handler.
Single‑select from presets or custom numeric input.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import (
    safe_edit,
    get_draft,
    get_user_data,
    handle_numeric_input,
    SELECT_REPEAT,
)
from .menus import build_repeat_keyboard, build_numeric_keyboard


async def show_repeat(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display repeat interval selection menu with current selection shown."""
    draft = get_draft(context)
    current: int | None = draft.get("repeat_interval")

    if current is not None:
        label = f"{current}m"
        text = f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):"
    else:
        text = "⏱️ Select interval (or use Custom):"

    await safe_edit(query, text, reply_markup=build_repeat_keyboard(current))
    return SELECT_REPEAT


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
    draft = get_draft(context)

    # ─── Custom ──────────────────────────────────────────────
    if action == "custom":
        user_data = get_user_data(context)
        user_data["num_field"] = "repeat"
        user_data["num_buffer"] = ""
        text = "✏️ Enter interval in seconds (number):\n\n \n\n(use the keypad below)"
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
        if draft.get("repeat_interval") is None:
            await safe_edit(
                query,
                "❌ Please select an interval or use 'Custom'.",
                reply_markup=build_repeat_keyboard(None),
            )
            return SELECT_REPEAT
        from .confirm_handler import show_confirm
        return await show_confirm(query, context)

    # ─── Done ─────────────────────────────────────────────────
    if action == "done":
        from .control_menus import show_main_menu
        await safe_edit(query, f"✅ Repeat interval set to {draft.get('repeat_interval')} minutes.")
        return await show_main_menu(query, context)

    # ─── Cancel ───────────────────────────────────────────────
    if data == "cancel":
        from .control_menus import show_main_menu
        await safe_edit(query, "Returning to main menu.")
        return await show_main_menu(query, context)

    # ─── Preset value ─────────────────────────────────────────
    try:
        minutes = int(action)
        draft["repeat_interval"] = minutes
        label = f"{minutes}m"
        await safe_edit(
            query,
            f"⏱️ Selected interval: {label}\n\nSelect interval (or use Custom):",
            reply_markup=build_repeat_keyboard(minutes),
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