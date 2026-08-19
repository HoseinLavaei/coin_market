"""
Conversation logic for Broadcast Bot menus.
Reuses selection_handlers and volume_handler, only overrides "Next" and numeric wrapper.
Activation uses numeric keypad (6-digit).
"""

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler

from .broadcast_confirm_handler import show_broadcast_confirm, broadcast_confirm_callback
from .common import safe_edit, get_draft, clear_draft, get_user_data
from .menus import (
    build_broadcast_main_menu,
    build_volume_keyboard,
    build_numeric_keyboard,
    SELECT_PROVIDER,
    SELECT_TYPE,
    SELECT_VOLUME,
    CONFIRM,
)
from .selection_handlers import show_selection, selection_callback
from .volume_handler import volume_callback, numeric_callback as volume_numeric_callback
from ..broadcast_bot_help_text import get_broadcast_help_text
from ...domain.value_objects import build_subscription_description
from ...infrastructure.repositories import claim_pending_subscription, add_subscription, delete_pending_subscription
from ...services.subscription_scheduler import schedule_subscription_job, get_job_queue, send_market_data

# ─── Custom states for broadcast ─────────────────────────────
BCAST_ACTIVATE_KEY = 40


# ─── Helper: render activation keypad ────────────────────────

async def _render_keypad_message(query, num_buffer: str) -> None:
    """Update the keypad message with the current buffer."""
    text = f"🔑 **Activate a Subscription**\n\nPlease enter the 6-digit activation key:\n\n`{num_buffer or ' '}`\n\n(use the keypad below)"
    await safe_edit(
        query,
        text,
        reply_markup=build_numeric_keyboard(include_negative=False, allow_decimal=False),
        parse_mode="Markdown",
    )


# ─── Helper: process activation confirm ─────────────────────

async def _process_activation_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, num_buffer: str) -> int:
    """Handle the 'Next' button on the activation keypad."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    if not num_buffer:
        await safe_edit(query, "❌ Please enter a key.")
        return BCAST_ACTIVATE_KEY

    if len(num_buffer) != 6 or not num_buffer.isdigit():
        await safe_edit(query, "❌ Please enter a valid 6-digit key.")
        return BCAST_ACTIVATE_KEY

    key = num_buffer
    chat = update.effective_chat
    if not chat:
        await safe_edit(query, "❌ Could not determine chat.")
        return ConversationHandler.END
    chat_id = chat.id

    data = await claim_pending_subscription(key, chat_id)
    if data is None:
        await safe_edit(
            query,
            "❌ Invalid or expired key. Please request a new one from the Control Bot, "
            "then try again."
        )
        return ConversationHandler.END

    try:
        sub = await add_subscription(
            chat_id=data["chat_id"],
            user_id=data["user_id"],
            provider=data["provider"],
            type_filter=data["type_filter"],
            volume=data["volume"],
            repeat_interval=data["repeat_interval"],
        )
        await delete_pending_subscription(key)

        job_queue = get_job_queue()
        if job_queue is None:
            await safe_edit(query, "❌ Job queue not available.")
            return ConversationHandler.END

        schedule_subscription_job(job_queue, sub)

        # ─── Send first update ─────────────────────────────
        dummy_context = type("DummyContext", (), {"bot": context.bot})()
        try:
            await send_market_data(
                chat_id=sub.chat_id,
                context=dummy_context,
                provider=sub.provider,
                type_filter=sub.type_filter,
                volume=sub.volume,
                is_auto=True,
            )
        except Exception as e:
            print(f"⚠️ First update failed for subscription #{sub.id}: {e}")

        filter_desc = build_subscription_description(
            data["provider"],
            data["type_filter"],
            data["volume"],
            data["repeat_interval"],
        )
        await safe_edit(
            query,
            f"✅ Subscription activated!\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {data['repeat_interval']}s\n"
            f"You will receive updates here."
        )
        user_data = get_user_data(context)
        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)
        return ConversationHandler.END

    except Exception as e:
        await safe_edit(query, f"❌ Failed to create subscription: {e}")
        return ConversationHandler.END


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


# ─── Main Menu display ──────────────────────────────────────

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


# ─── Activate Subscription with Numeric Keypad ─────────────

async def start_activate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Activate Subscription' button – show numeric keypad for key entry."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    user_data = get_user_data(context)
    user_data["num_field"] = "key"
    user_data["num_buffer"] = ""

    await _render_keypad_message(query, "")
    return BCAST_ACTIVATE_KEY


async def handle_activate_key_numeric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle numeric keypad input for activation key.
    When user presses 'Next', claim the pending subscription.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data or not data.startswith("num:"):
        return BCAST_ACTIVATE_KEY

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    num_buffer = user_data.get("num_buffer", "")

    # ─── Backspace ──────────────────────────────────────────
    if action == "backspace":
        num_buffer = num_buffer[:-1]
        user_data["num_buffer"] = num_buffer
        await _render_keypad_message(query, num_buffer)
        return BCAST_ACTIVATE_KEY

    # ─── Digit ──────────────────────────────────────────────
    if action.isdigit():
        num_buffer += action
        user_data["num_buffer"] = num_buffer
        await _render_keypad_message(query, num_buffer)
        return BCAST_ACTIVATE_KEY

    # ─── Next (Confirm) ────────────────────────────────────
    if action == "next":
        return await _process_activation_confirm(update, context, num_buffer)

    # ─── Back ──────────────────────────────────────────────
    if action == "back":
        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)
        await show_broadcast_main_menu(update, context)
        return ConversationHandler.END

    # ─── Cancel ─────────────────────────────────────────────
    if data == "cancel":
        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)
        await safe_edit(query, "❌ Activation cancelled.")
        return ConversationHandler.END

    return BCAST_ACTIVATE_KEY


# ─── Help ─────────────────────────────────────────────────────

async def start_broadcast_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show help text and end the conversation."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    help_text = get_broadcast_help_text()
    await safe_edit(query, help_text, parse_mode=None)
    return ConversationHandler.END


# ─── Main menu callback ──────────────────────────────────────

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

    if action == "activate":
        return await start_activate_subscription(update, context)

    if action == "help":
        return await start_broadcast_help(update, context)

    await safe_edit(query, "❌ Unknown action.")
    return ConversationHandler.END


# ─── Fallback for Cancel ────────────────────────────────────

async def broadcast_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        clear_draft(context)
        user_data = get_user_data(context)
        user_data.pop("num_buffer", None)
        user_data.pop("num_field", None)
        await safe_edit(query, "❌ Cancelled.")
    return ConversationHandler.END


# ─── Conversation Handler ────────────────────────────────────

broadcast_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(broadcast_main_menu_callback, pattern="^bcast:"),
        CommandHandler("start", show_broadcast_main_menu),
        CommandHandler("menu", show_broadcast_main_menu),
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
        BCAST_ACTIVATE_KEY: [
            CallbackQueryHandler(handle_activate_key_numeric, pattern="^num:"),
            CallbackQueryHandler(handle_activate_key_numeric, pattern="^cancel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(broadcast_cancel_handler, pattern="^cancel$"),
    ],
    per_message=False,
    per_chat=True,
    allow_reentry=True,
)
