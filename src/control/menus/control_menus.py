"""
Control Bot conversation handler.
Single subscription flow – directly enters provider selection.
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from .common import (
    safe_edit,
    get_draft,
    clear_draft,
    get_user_data,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    SELECT_REPEAT,
    CONFIRM,
)
from .confirm_handler import confirm_callback
from .menus import build_provider_keyboard
from .repeat_handler import repeat_callback, numeric_callback as repeat_numeric_callback
from .repeat_handler import show_repeat
from .selection_handlers import selection_callback
from .volume_handler import show_volume
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from ...db import get_subscription_for_user


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
    Then shows provider selection.
    """
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    # ─── Check if user has a subscription ──────────────────
    sub = await get_subscription_for_user(user.id)

    if sub is None:
        # No subscription – start with empty draft
        clear_draft(context)
        get_draft(context)
        message = update.effective_message
        if message:
            await message.reply_text(
                "🏛️ Select providers (toggle each, or use All/Clear):",
                reply_markup=build_provider_keyboard([]),
            )
        return SELECT_PROVIDER

    # ─── Has subscription – load existing values ──────────
    providers = sub.provider.split(",") if sub.provider else []
    types = sub.type_filter.split(",") if sub.type_filter else []

    draft = get_draft(context)
    draft["providers"] = providers
    draft["types"] = types
    draft["volume"] = sub.volume
    draft["repeat_interval"] = sub.repeat_interval

    message = update.effective_message
    if message:
        await message.reply_text(
            "✏️ Editing your subscription – select providers (toggle each, or use All/Clear):",
            reply_markup=build_provider_keyboard(providers),
        )
    return SELECT_PROVIDER


# ─── Cancel Handler ──────────────────────────────────────

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle global cancel."""
    query = update.callback_query
    if query:
        await query.answer()
        clear_draft(context)
        user_data = get_user_data(context)
        user_data.pop("stop_selected", None)
        user_data.pop("resume_selected", None)
        user_data.pop("delete_selected", None)
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
