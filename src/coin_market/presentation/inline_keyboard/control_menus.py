"""
Conversation logic for Control Bot menus.
Uses builders from .menus and handlers from selection_handlers, volume_handler, repeat_handler, chat_handler, confirm_handler.
Entry point: /start
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from .chat_handler import (
    show_chat,
    chat_callback,
    numeric_callback as chat_numeric_callback,
)
from .common import safe_edit, get_draft, clear_draft
from .confirm_handler import (
    confirm_callback,
)
from .menus import (
    build_control_main_menu,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    SELECT_REPEAT,
    SELECT_CHAT,
    CONFIRM,
)
from .repeat_handler import (
    show_repeat,
    repeat_callback,
    numeric_callback as repeat_numeric_callback,
)
from .selection_handlers import (
    show_selection,
    selection_callback,
)
from .volume_handler import (
    show_volume,
    volume_callback,
    numeric_callback as volume_numeric_callback,
)
from ...domain.value_objects import build_subscription_description
from ...infrastructure.repositories import get_subscriptions_for_user


# ─── Numeric Callback Wrappers ─────────────────────────────

async def volume_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for volume numeric callback."""
    result = await volume_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_volume(query, context)
    return result


async def repeat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for repeat numeric callback."""
    result = await repeat_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_repeat(query, context)
    return result


async def chat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for chat numeric callback."""
    result = await chat_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_chat(query, context)
    return result


# ─── Main Menu ──────────────────────────────────────────────

async def show_main_menu(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    message = update.effective_message

    if query:
        await query.answer()
        await safe_edit(
            query,
            "🤖 Control Bot – Main Menu\n\nSelect an action:",
            reply_markup=build_control_main_menu(),
        )
    elif message:
        await message.reply_text(
            "🤖 Control Bot – Main Menu\n\nSelect an action:",
            reply_markup=build_control_main_menu(),
        )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return ConversationHandler.END

    action = data.split(":")[1] if data.startswith("main:") else None

    match action:
        case "new":
            clear_draft(context)
            get_draft(context)
            return await show_selection(query, context, "prov")
        case "list":
            await list_subscriptions(update, context)
            return ConversationHandler.END
        case "stop":
            await safe_edit(query, "⏸️ Stop Subscription (coming soon)")
            return ConversationHandler.END
        case "resume":
            await safe_edit(query, "▶️ Resume Subscription (coming soon)")
            return ConversationHandler.END
        case "edit":
            await safe_edit(query, "✏️ Edit Subscription (coming soon)")
            return ConversationHandler.END
        case "delete":
            await safe_edit(query, "🗑️ Delete Subscription (coming soon)")
            return ConversationHandler.END
        case "help":
            await safe_edit(query, "❓ Help (coming soon)")
            return ConversationHandler.END
        case _:
            await safe_edit(query, "❌ Unknown action.")
            return ConversationHandler.END


# ─── List Subscriptions ─────────────────────────────────────

async def list_subscriptions(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return

    subs = await get_subscriptions_for_user(user.id)
    if not subs:
        await safe_edit(query, "📭 You have no subscriptions.")
        return

    lines = ["📋 Your subscriptions:"]
    for sub in subs:
        status_emoji = "✅" if sub.status == "active" else "⏸️"
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        lines.append(f"  {status_emoji} #{sub.id}: {desc} (chat: {sub.chat_id})")

    await safe_edit(query, "\n".join(lines))


# ─── Fallback for Cancel ────────────────────────────────────

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        clear_draft(context)
        await safe_edit(query, "❌ Cancelled.")
    return ConversationHandler.END


# ─── Conversation Handler ────────────────────────────────────

control_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(main_menu_callback, pattern="^main:"),
        CommandHandler("start", show_main_menu),
    ],
    states={
        SELECT_PROVIDER: [
            CallbackQueryHandler(
                lambda u, c: selection_callback(u, c, show_main_menu),
                pattern="^prov"
            ),
        ],
        SELECT_TYPE: [
            CallbackQueryHandler(
                lambda u, c: selection_callback(u, c, show_main_menu),
                pattern="^type"
            ),
        ],
        SELECT_VOLUME: [
            CallbackQueryHandler(volume_callback, pattern="^vol:"),
            CallbackQueryHandler(volume_numeric_wrapper, pattern="^num:"),
        ],
        SELECT_REPEAT: [
            CallbackQueryHandler(repeat_callback, pattern="^rep:"),
            CallbackQueryHandler(repeat_numeric_wrapper, pattern="^num:"),
        ],
        SELECT_CHAT: [
            CallbackQueryHandler(chat_callback, pattern="^chat:"),
            CallbackQueryHandler(chat_numeric_wrapper, pattern="^num:"),
        ],
        CONFIRM: [
            CallbackQueryHandler(confirm_callback, pattern="^confirm:"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
    per_message=False,
    per_chat=True,
    allow_reentry=True,
)
