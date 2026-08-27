"""
Volume selection handler.
Single‑select from presets or custom numeric input.
"""

from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, get_user_data, SELECT_VOLUME
from .menus import build_volume_keyboard, build_numeric_keyboard


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
    draft = get_draft(context)

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
        if draft.get("volume") is None:
            await safe_edit(
                query,
                "❌ Please select a volume or use 'Custom'.",
                reply_markup=build_volume_keyboard(None),
            )
            return SELECT_VOLUME
        from .repeat_handler import show_repeat
        return await show_repeat(query, context)

    # ─── Done ─────────────────────────────────────────────────
    if action == "done":
        # Save current volume and return to main menu
        from .control_menus import show_main_menu
        await safe_edit(query, f"✅ Volume set to {draft.get('volume')}.")
        return await show_main_menu(query, context)

    # ─── Cancel ───────────────────────────────────────────────
    if data == "cancel":
        # Return to main menu without saving
        from .control_menus import show_main_menu
        await safe_edit(query, "Returning to main menu.")
        return await show_main_menu(query, context)

    # ─── Preset value ─────────────────────────────────────────
    try:
        value = Decimal(action)
        draft["volume"] = value
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