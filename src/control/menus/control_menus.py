"""
Control Bot conversation handler.
Dashboard‑style main menu with auto‑save.
"""

import secrets

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from db.subscription_repository import create_or_replace_pending
from src import logger
from src.subscription_types import SubscriptionData
from .common import (
    safe_edit,
    get_user_data,
    MAIN_MENU,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    SELECT_REPEAT,
    get_current_subscription,
)
from .menus import build_main_menu_keyboard, build_provider_keyboard
from .repeat_handler import repeat_callback, numeric_callback as repeat_numeric_callback
from .repeat_handler import show_repeat
from .selection_handlers import selection_callback
from .volume_handler import show_volume
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from ...db import get_subscription_for_user


# ─── Helper to refresh subscription from DB ───────────────────

async def _refresh_subscription_from_db(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Refresh the cached subscription data from the database."""
    sub_orm = await get_subscription_for_user(user_id)
    user_data = get_user_data(context)
    if sub_orm:
        sub_data = SubscriptionData(
            id=sub_orm.id,
            chat_id=sub_orm.chat_id,
            provider=sub_orm.provider,
            type_filter=sub_orm.type_filter,
            volume=sub_orm.volume,
            repeat_interval=sub_orm.repeat_interval,
        )
        user_data["current_subscription"] = sub_data
        user_data["is_new"] = sub_orm.chat_id is None
        if sub_orm.activation_key:
            user_data["activation_key"] = sub_orm.activation_key
    else:
        user_data["current_subscription"] = None
        user_data["is_new"] = True


# ─── Helper to build main menu text ────────────────────────

def _build_main_menu_text(sub: SubscriptionData | None) -> str:
    if sub:
        providers = ", ".join(sub.provider.split(",")) if sub.provider else "None"
        types = ", ".join(sub.type_filter.split(",")) if sub.type_filter else "None"
        volume_str = format(sub.volume, "f") if sub.volume is not None else "Not set"
        repeat_str = f"every {sub.repeat_interval} minute(s)" if sub.repeat_interval else "Not set"
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


def _should_show_confirm(sub: SubscriptionData | None, is_new: bool) -> bool:
    if not is_new or sub is None:
        return False
    return (
            sub.provider is not None
            and sub.type_filter is not None
            and sub.volume is not None
            and sub.repeat_interval is not None
    )


# ─── Helper to show main menu ─────────────────────────────

async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = get_user_data(context)
    user_id = user_data.get("user_id")
    if isinstance(user_id, int):
        await _refresh_subscription_from_db(context, user_id)

    sub = get_current_subscription(context)
    is_new = bool(user_data.get("is_new", False))
    show_confirm = _should_show_confirm(sub, is_new)
    activation_key = user_data.get("activation_key")

    text = _build_main_menu_text(sub)
    await safe_edit(
        query,
        text,
        reply_markup=build_main_menu_keyboard(show_confirm, activation_key),
        parse_mode="HTML"
    )
    return MAIN_MENU


# ─── Numeric Wrappers ──────────────────────────────────────

async def _volume_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = await volume_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_volume(query, context)
    return result


async def _repeat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = await repeat_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_repeat(query, context)
    return result


# ─── Entry Point ──────────────────────────────────────────

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    user_id = user.id

    sub_orm = await get_subscription_for_user(user_id)

    if sub_orm is None:
        activation_key = str(secrets.randbelow(1000000)).zfill(6)
        sub_orm = await create_or_replace_pending(
            user_id=user_id,
            provider=None,
            type_filter=None,
            volume=None,
            repeat_interval=None,
            key=activation_key,
        )
        logger.info(f"Created new pending subscription for user {user_id} with key {activation_key}")
    else:
        if sub_orm.activation_key is None:
            activation_key = str(secrets.randbelow(1000000)).zfill(6)
            sub_orm = await create_or_replace_pending(
                user_id=user_id,
                provider=sub_orm.provider,
                type_filter=sub_orm.type_filter,
                volume=sub_orm.volume,
                repeat_interval=sub_orm.repeat_interval,
                key=activation_key,
            )
            logger.info(f"Generated key for existing pending subscription of user {user_id}")
        else:
            activation_key = sub_orm.activation_key

    sub_data = SubscriptionData(
        id=sub_orm.id,
        chat_id=sub_orm.chat_id,
        provider=sub_orm.provider,
        type_filter=sub_orm.type_filter,
        volume=sub_orm.volume,
        repeat_interval=sub_orm.repeat_interval,
    )
    is_new = sub_orm.chat_id is None

    user_data = get_user_data(context)
    user_data["user_id"] = user_id
    user_data["is_new"] = is_new
    user_data["current_subscription"] = sub_data
    user_data["activation_key"] = activation_key

    message = update.effective_message
    if message:
        text = _build_main_menu_text(sub_data)
        show_confirm = _should_show_confirm(sub_data, is_new)
        await message.reply_text(
            text,
            reply_markup=build_main_menu_keyboard(show_confirm, activation_key),
            parse_mode="HTML"
        )
    return MAIN_MENU


# ─── Main Menu Callback ────────────────────────────────────

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return MAIN_MENU
    await query.answer()

    data = query.data
    if not data or not data.startswith("menu:"):
        return MAIN_MENU

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    user_id = user_data.get("user_id")
    if isinstance(user_id, int):
        await _refresh_subscription_from_db(context, user_id)

    sub = get_current_subscription(context)
    if sub is None:
        await safe_edit(query, "❌ Subscription data not found.")
        return MAIN_MENU

    activation_key = user_data.get("activation_key")

    if action == "providers":
        selected = sub.provider.split(",") if sub.provider else []
        await safe_edit(query, "🏛️ Select providers (toggle each):",
                        reply_markup=build_provider_keyboard(selected, False, activation_key))
        return SELECT_PROVIDER

    if action == "types":
        from .menus import build_type_keyboard
        selected = sub.type_filter.split(",") if sub.type_filter else []
        await safe_edit(query, "📊 Select types (toggle each):",
                        reply_markup=build_type_keyboard(selected, False, activation_key))
        return SELECT_TYPE

    if action == "volume":
        return await show_volume(query, context)

    if action == "repeat":
        return await show_repeat(query, context)

    return MAIN_MENU


# ─── Fallback for /cancel ──────────────────────────────────

async def cancel_fallback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
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
    },
    fallbacks=[
        CommandHandler("cancel", cancel_fallback),
    ],
    per_chat=True,
    allow_reentry=True,
)
