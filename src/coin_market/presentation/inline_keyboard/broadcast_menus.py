"""
Conversation logic for Broadcast Bot menus.
Reuses selection_handlers and volume_handler, only overrides "Next" and numeric wrapper.
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler

from .menus import (
    build_broadcast_main_menu,
    build_volume_keyboard,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    CONFIRM,
)
from .common import safe_edit, get_draft, clear_draft
from .selection_handlers import show_selection, selection_callback
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from .broadcast_confirm_handler import show_broadcast_confirm, broadcast_confirm_callback


# ─── Custom volume "next" handler ─────────────────────────────

async def broadcast_volume_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Next' on volume selection – go to confirm."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    draft = get_draft(context)
    if draft.get("volume") is None:
        await safe_edit(
            query,
            "❌ Please select a volume or use 'Custom'.",
            reply_markup=build_volume_keyboard(None)
        )
        return SELECT_VOLUME
    return await show_broadcast_confirm(query, context)


# ─── Custom numeric wrapper ─────────────────────────────────

async def broadcast_volume_numeric_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Wrapper around volume_numeric_callback.
    After numeric entry (when it returns END), go to confirm instead of showing volume again.
    """
    result = await volume_numeric_callback(update, context)
    if result == ConversationHandler.END:
        query = update.callback_query
        if query:
            return await show_broadcast_confirm(query, context)
    return result


# ─── Main Menu display (standalone, called from broadcast_bot.py) ──

async def show_broadcast_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the main menu. Works for both messages and channel posts."""
    query = update.callback_query
    message = update.effective_message
    chat = update.effective_chat
    if not chat:
        return

    text = "🤖 Broadcast Bot – Main Menu\n\nSelect an action:"
    keyboard = build_broadcast_main_menu()

    if query:
        await query.answer()
        await safe_edit(query, text, reply_markup=keyboard)
    elif message and chat:
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            reply_markup=keyboard
        )


# ─── Main menu callback – starts the conversation ──────────────

async def broadcast_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle main menu button clicks. Returns the next conversation state."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data or not data.startswith("bcast:"):
        return ConversationHandler.END

    action = data.split(":", 1)[1]

    if action == "prices":
        clear_draft(context)
        get_draft(context)
        return await show_selection(query, context, "prov")

    elif action == "activate":
        from ..broadcast_bot_help_text import get_broadcast_help_text
        await safe_edit(
            query,
            "🔑 **Activate a Subscription**\n\n"
            "To activate a pending subscription, send the key you received from the Control Bot:\n"
            "`/conf <KEY>`\n\n"
            "If you don't have a key, create one using the Control Bot with `/prices --repeat SEC`.\n\n"
            "_(The key is valid for a limited time.)_",
            parse_mode="Markdown",
            reply_markup=build_broadcast_main_menu(),
        )
        return ConversationHandler.END

    elif action == "help":
        from ..broadcast_bot_help_text import get_broadcast_help_text
        await safe_edit(query, get_broadcast_help_text(), parse_mode=None)
        return ConversationHandler.END

    else:
        await safe_edit(query, "❌ Unknown action.")
        return ConversationHandler.END


# ─── Fallback for Cancel ────────────────────────────────────

async def broadcast_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        clear_draft(context)
        await safe_edit(query, "❌ Cancelled.")
    return ConversationHandler.END


# ─── Conversation Handler ────────────────────────────────────

broadcast_conversation = ConversationHandler(
    entry_points=[
        # Only callback queries start the conversation
        CallbackQueryHandler(broadcast_main_menu_callback, pattern="^bcast:"),
    ],
    states={
        SELECT_PROVIDER: [
            CallbackQueryHandler(
                lambda u, c: selection_callback(u, c, show_broadcast_main_menu),
                pattern="^prov"
            ),
        ],
        SELECT_TYPE: [
            CallbackQueryHandler(
                lambda u, c: selection_callback(u, c, show_broadcast_main_menu),
                pattern="^type"
            ),
        ],
        SELECT_VOLUME: [
            CallbackQueryHandler(broadcast_volume_next, pattern="^vol:next$"),
            CallbackQueryHandler(volume_callback, pattern="^vol:"),
            CallbackQueryHandler(broadcast_volume_numeric_wrapper, pattern="^num:"),
        ],
        CONFIRM: [
            CallbackQueryHandler(broadcast_confirm_callback, pattern="^bcast_confirm:"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(broadcast_cancel_handler, pattern="^cancel$"),
    ],
    per_message=False,
    per_chat=True,
    allow_reentry=True,
)