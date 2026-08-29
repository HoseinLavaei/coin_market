"""
Control Bot conversation handler.
Dashboard‑style main menu with auto‑save.
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

import logger
from .common import (
    safe_edit,
    get_user_data,
    MAIN_MENU,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    SELECT_REPEAT,
    CONFIRM,
)
from .confirm_handler import confirm_callback, perform_activation
from .menus import build_main_menu_keyboard, build_provider_keyboard
from .repeat_handler import repeat_callback, numeric_callback as repeat_numeric_callback
from .repeat_handler import show_repeat
from .selection_handlers import selection_callback
from .volume_handler import show_volume
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from ...db import get_subscription_for_user
from ...db.repositories.subscription_repository import save_subscription_settings


# ─── Helper to build main menu text ────────────────────────

def _build_main_menu_text(sub: dict | None) -> str:
    if sub:
        providers = ", ".join(sub.get("provider", "").split(",")) if sub.get("provider") else "None"
        types = ", ".join(sub.get("type_filter", "").split(",")) if sub.get("type_filter") else "None"
        volume = sub.get("volume")
        volume_str = str(volume) if volume is not None else "Not set"
        repeat = sub.get("repeat_interval")
        repeat_str = f"every {repeat} minute(s)" if repeat else "Not set"
    else:
        providers = "None"
        types = "None"
        volume_str = "Not set"
        repeat_str = "Not set"

    return (
        "<b>📋 Your Subscription Settings</b>\n\n"
        f"Providers:  {providers}\n"
        f"Types:      {types}\n"
        f"Volume:     {volume_str}\n"
        f"Repeat:     {repeat_str}\n\n"
        "Choose an option below:"
    )


# ─── Helper to show main menu ─────────────────────────────

async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the main menu with current settings."""
    user_data = get_user_data(context)
    sub = user_data.get("current_subscription")
    is_new = user_data.get("is_new", False)

    text = _build_main_menu_text(sub)
    await safe_edit(query, text, reply_markup=build_main_menu_keyboard(show_done=is_new), parse_mode="HTML")
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
    Loads or creates a subscription from DB, then shows the main menu.
    """
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    user_id = user.id

    # ─── Check if user has a subscription ──────────────────
    sub = await get_subscription_for_user(user_id)

    if sub is None:
        # Create a new pending subscription with defaults
        sub = await save_subscription_settings(
            user_id=user_id,
            provider=None,
            type_filter=None,
            volume=None,
            repeat_interval=None,
            chat_id=None,
        )
        logger.info(f"Created new pending subscription for user {user_id}")

    # ─── Store in user_data ──────────────────────────────────
    user_data = get_user_data(context)
    user_data["user_id"] = user_id
    user_data["is_new"] = sub.chat_id is None  # True if no chat_id
    user_data["current_subscription"] = {
        "id": sub.id,
        "user_id": sub.user_id,
        "chat_id": sub.chat_id,
        "provider": sub.provider,
        "type_filter": sub.type_filter,
        "volume": sub.volume,
        "repeat_interval": sub.repeat_interval,
        "last_sent_at": sub.last_sent_at,
        "activation_key": sub.activation_key,
        "expires_at": sub.expires_at,
    }

    # Show main menu
    message = update.effective_message
    if message:
        text = _build_main_menu_text(user_data["current_subscription"])
        await message.reply_text(
            text,
            reply_markup=build_main_menu_keyboard(show_done=user_data["is_new"]),
            parse_mode="HTML"
        )
    return MAIN_MENU


# ─── Validation and activation helpers ─────────────────────

def _check_missing_fields(sub: dict) -> list[str]:
    """Return a list of missing required field names."""
    missing = []
    if not sub.get("provider"):
        missing.append("Providers")
    if not sub.get("type_filter"):
        missing.append("Types")
    if sub.get("volume") is None:
        missing.append("Volume")
    if sub.get("repeat_interval") is None:
        missing.append("Repeat interval")
    return missing


async def _handle_done_action(
        query,
        _context: ContextTypes.DEFAULT_TYPE,
        user_data: dict,
        sub: dict,
        is_new: bool,
) -> int:
    """Handle the Done button for new users."""
    if not is_new:
        await safe_edit(query, "❌ You already have an active subscription.")
        return MAIN_MENU

    missing = _check_missing_fields(sub)
    if missing:
        await safe_edit(
            query,
            f"❌ Please set: {', '.join(missing)} before activating.",
            reply_markup=build_main_menu_keyboard(show_done=True),
            parse_mode="HTML"
        )
        return MAIN_MENU

    # All fields are set, proceed to activation
    return await perform_activation(query, user_data["user_id"], sub)


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
    user_data = get_user_data(context)
    sub = user_data.get("current_subscription")
    if not isinstance(sub, dict):
        # Should not happen, but guard
        await safe_edit(query, "❌ Subscription data not found.")
        return MAIN_MENU

    is_new = user_data.get("is_new", False)

    if action == "providers":
        selected = sub.get("provider", "").split(",") if sub.get("provider") else []
        await safe_edit(query, "🏛️ Select providers (toggle each):",
                        reply_markup=build_provider_keyboard(selected))
        return SELECT_PROVIDER

    if action == "types":
        from .menus import build_type_keyboard
        selected = sub.get("type_filter", "").split(",") if sub.get("type_filter") else []
        await safe_edit(query, "📊 Select types (toggle each):",
                        reply_markup=build_type_keyboard(selected))
        return SELECT_TYPE

    if action == "volume":
        return await show_volume(query, context)

    if action == "repeat":
        return await show_repeat(query, context)

    if action == "done":
        return await _handle_done_action(query, context, user_data, sub, is_new)

    return MAIN_MENU


# ─── Fallback for /cancel ──────────────────────────────────

async def cancel_fallback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """Simple cancel handler that ends the conversation."""
    query = update.callback_query
    if query:
        await query.answer()
        await safe_edit(query, "❌ Cancelled.")
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
        CommandHandler("cancel", cancel_fallback),
    ],
    per_chat=True,
    allow_reentry=True,
)
