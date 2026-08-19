"""
Conversation logic for Control Bot menus.
Uses builders from .menus and handlers from selection_handlers, volume_handler, repeat_handler, chat_handler, confirm_handler,
stop_handler, resume_handler, edit_handler, delete_handler, help_handler.
Entry point: /start
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from .chat_handler import (
    show_chat,
    chat_callback,
    numeric_callback as chat_numeric_callback,
)
from .common import safe_edit, get_draft, clear_draft, get_user_data, SELECT_EDIT_SUB
from .confirm_handler import (
    confirm_callback,
)
from .delete_handler import (
    delete_subscription_menu,
    delete_callback,
    delete_confirm_callback,
    SELECT_DELETE_SUB,
    CONFIRM_DELETE,
)
from .edit_handler import (
    edit_subscription_menu,
    edit_selection_callback,
)
from .help_handler import (
    show_help,
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
from .resume_handler import (
    resume_subscription_menu,
    resume_callback,
    resume_confirm_callback,
    SELECT_RESUME_SUB,
    CONFIRM_RESUME,
)
from .selection_handlers import (
    show_selection,
    selection_callback,
)
from .stop_handler import (
    stop_subscription_menu,
    stop_callback,
    stop_confirm_callback,
    SELECT_STOP_SUB,
    CONFIRM_STOP,
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
    result = await volume_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_volume(query, context)
    return result


async def repeat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = await repeat_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_repeat(query, context)
    return result


async def chat_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
            return await stop_subscription_menu(update, context)
        case "resume":
            return await resume_subscription_menu(update, context)
        case "edit":
            return await edit_subscription_menu(update, context)
        case "delete":
            return await delete_subscription_menu(update, context)
        case "help":
            return await show_help(update, context)
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
        user_data = get_user_data(context)
        user_data.pop("stop_selected", None)
        user_data.pop("resume_selected", None)
        user_data.pop("delete_selected", None)
        await safe_edit(query, "❌ Cancelled.")
    return ConversationHandler.END


# ─── Conversation Handler ────────────────────────────────────

control_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(main_menu_callback, pattern="^main:"),
        CommandHandler("start", show_main_menu),
        CommandHandler("menu", show_main_menu),  # Added this line
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
        SELECT_STOP_SUB: [
            CallbackQueryHandler(stop_callback, pattern="^stop"),
        ],
        CONFIRM_STOP: [
            CallbackQueryHandler(stop_confirm_callback, pattern="^stop_confirm:"),
        ],
        SELECT_RESUME_SUB: [
            CallbackQueryHandler(resume_callback, pattern="^resume"),
        ],
        CONFIRM_RESUME: [
            CallbackQueryHandler(resume_confirm_callback, pattern="^resume_confirm:"),
        ],
        SELECT_EDIT_SUB: [
            CallbackQueryHandler(edit_selection_callback, pattern="^edit_sel:"),
            CallbackQueryHandler(edit_selection_callback, pattern="^edit_cancel"),
        ],
        SELECT_DELETE_SUB: [
            CallbackQueryHandler(delete_callback, pattern="^delete"),
        ],
        CONFIRM_DELETE: [
            CallbackQueryHandler(delete_confirm_callback, pattern="^delete_confirm:"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
    per_message=False,
    per_chat=True,
    allow_reentry=True,
)
