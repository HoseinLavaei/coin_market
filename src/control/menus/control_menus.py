"""
Control Bot conversation handler.
New dashboard‑style main menu.
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from .common import (
    safe_edit,
    get_draft,
    clear_draft,
    MAIN_MENU,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    SELECT_REPEAT,
    CONFIRM,
)
from .confirm_handler import confirm_callback, show_confirm
from .menus import build_main_menu_keyboard, build_provider_keyboard
from .repeat_handler import repeat_callback, numeric_callback as repeat_numeric_callback
from .repeat_handler import show_repeat
from .selection_handlers import selection_callback
from .volume_handler import show_volume
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from ...db import get_subscription_for_user


# ─── Helper to build main menu text ────────────────────────

def _build_main_menu_text(draft: dict) -> str:
    provider_str = ", ".join(draft.get("providers", [])) or "None"
    type_str = ", ".join(draft.get("types", [])) or "None"
    volume = draft.get("volume")
    volume_str = str(volume) if volume is not None else "Not set"
    repeat = draft.get("repeat_interval")
    repeat_str = f"every {repeat} minute(s)" if repeat else "Not set"

    return (
        "<b>📋 Your Subscription Settings</b>\n\n"
        f"Providers:  {provider_str}\n"
        f"Types:      {type_str}\n"
        f"Volume:     {volume_str}\n"
        f"Repeat:     {repeat_str}\n\n"
        "Choose an option below:"
    )


# ─── Helper to show main menu ─────────────────────────────

async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the main menu with current settings."""
    draft = get_draft(context)
    text = _build_main_menu_text(draft)
    await safe_edit(query, text, reply_markup=build_main_menu_keyboard(), parse_mode="HTML")
    return MAIN_MENU


# ─── Numeric Wrappers ──────────────────────────────────────

async def _volume_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for volume numeric callback to stay in correct state."""
    result = await volume_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_volume(query, context)
    return result


async def _repeat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for repeat numeric callback to stay in correct state."""
    result = await repeat_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_repeat(query, context)
    return result


# ─── Entry Point ──────────────────────────────────────────

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for /start and /menu.
    - If user has subscription: loads existing values into draft.
    - If no subscription: starts with empty draft.
    Then shows the main menu.
    """
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    # ─── Check if user has a subscription ──────────────────
    sub = await get_subscription_for_user(user.id)

    draft = get_draft(context)
    if sub:
        draft["providers"] = sub.provider.split(",") if sub.provider else []
        draft["types"] = sub.type_filter.split(",") if sub.type_filter else []
        draft["volume"] = sub.volume
        draft["repeat_interval"] = sub.repeat_interval
    else:
        clear_draft(context)  # start empty

    # Show main menu
    message = update.effective_message
    if message:
        text = _build_main_menu_text(draft)
        await message.reply_text(text, reply_markup=build_main_menu_keyboard(), parse_mode="HTML")
    return MAIN_MENU


# ─── Main Menu Callback ────────────────────────────────────

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle main menu button presses."""
    query = update.callback_query
    if not query:
        return MAIN_MENU
    await query.answer()
    data = query.data
    if not data or not data.startswith("menu:"):
        return MAIN_MENU

    action = data.split(":", 1)[1]
    draft = get_draft(context)

    if action == "providers":
        await safe_edit(query, "🏛️ Select providers (toggle each):",
                        reply_markup=build_provider_keyboard(draft.get("providers", [])))
        return SELECT_PROVIDER

    if action == "types":
        from .menus import build_type_keyboard
        await safe_edit(query, "📊 Select types (toggle each):",
                        reply_markup=build_type_keyboard(draft.get("types", [])))
        return SELECT_TYPE

    if action == "volume":
        return await show_volume(query, context)

    if action == "repeat":
        return await show_repeat(query, context)

    if action == "confirm":
        return await show_confirm(query, context)

    if action == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Cancelled.")
        return ConversationHandler.END

    return MAIN_MENU


# ─── Cancel Handler ──────────────────────────────────────

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle global cancel – returns to main menu unless we're already there."""
    query = update.callback_query
    if query:
        await query.answer()
        # Return to main menu
        await safe_edit(query, "Returning to main menu.")
        return await show_main_menu(query, context)
    else:
        message = update.effective_message
        if message:
            await message.reply_text("❌ Cancelled.")
        return ConversationHandler.END


# ─── Conversation Handler ──────────────────────────────

control_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("start", start_subscription_flow),
        CommandHandler("menu", start_subscription_flow),
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(main_menu_callback, pattern="^menu:"),
        ],
        SELECT_PROVIDER: [
            CallbackQueryHandler(selection_callback, pattern="^prov"),
        ],
        SELECT_TYPE: [
            CallbackQueryHandler(selection_callback, pattern="^type"),
        ],
        SELECT_VOLUME: [
            CallbackQueryHandler(volume_callback, pattern="^vol:"),
            CallbackQueryHandler(_volume_numeric_wrapper, pattern="^num:"),
        ],
        SELECT_REPEAT: [
            CallbackQueryHandler(repeat_callback, pattern="^rep:"),
            CallbackQueryHandler(_repeat_numeric_wrapper, pattern="^num:"),
        ],
        CONFIRM: [
            CallbackQueryHandler(confirm_callback, pattern="^confirm:"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
        CommandHandler("cancel", cancel_handler),
    ],
    per_chat=True,
    allow_reentry=True,
)