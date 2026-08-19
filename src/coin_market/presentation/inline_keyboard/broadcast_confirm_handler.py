"""
Broadcast bot confirm handler – shows summary and fetches data.
"""

from decimal import Decimal
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft
from .menus import CONFIRM
from ...domain.value_objects import build_subscription_description
from ...services.subscription_scheduler import send_market_data


# ─── Helper: safely extract chat_id from callback query ──────

def _get_chat_id(query) -> Optional[int]:
    """
    Safely extract chat_id from a callback query.
    Returns None if the message is inaccessible or lacks chat_id.
    """
    if query.message is None:
        return None
    # The message object from a callback query is usually a Message with chat_id.
    # But to satisfy the type checker, we check for hasattr.
    if hasattr(query.message, "chat_id"):
        return query.message.chat_id
    return None


# ─── Show confirm screen ──────────────────────────────────────

async def show_broadcast_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Display a summary of selected filters and a 'Fetch' button.
    This function receives the callback query directly (not an Update).
    """
    draft = get_draft(context)
    providers = draft.get("providers", [])
    type_filter = draft.get("types", [])
    volume = draft.get("volume")

    provider_str = ",".join(providers) if providers else None
    type_str = ",".join(type_filter) if type_filter else None

    summary = build_subscription_description(provider_str, type_str, volume, None)

    text = (
        "📋 **Review your filters**\n\n"
        f"{summary}\n\n"
        "Click 'Fetch' to get market data with these filters."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Fetch", callback_data="bcast_confirm:fetch")],
        [InlineKeyboardButton("🔙 Back", callback_data="bcast_confirm:back")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])
    await safe_edit(query, text, parse_mode=None, reply_markup=keyboard)
    return CONFIRM


# ─── Confirm callback (fetch or back) ────────────────────────

async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle 'Fetch' and 'Back' actions from the confirm screen.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    data = query.data
    if not data or not data.startswith("bcast_confirm:"):
        return ConversationHandler.END

    action = data.split(":", 1)[1]

    # ─── Back to volume selection ──────────────────────────────
    if action == "back":
        from .volume_handler import show_volume
        return await show_volume(query, context)

    # ─── Fetch prices ───────────────────────────────────────────
    if action == "fetch":
        chat_id = _get_chat_id(query)
        if chat_id is None:
            # Cannot proceed without a valid chat_id.
            await safe_edit(query, "❌ Unable to determine chat. Please try again.")
            return ConversationHandler.END

        draft = get_draft(context)
        provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
        type_filter = ",".join(draft.get("types", [])) if draft.get("types") else None
        volume = draft.get("volume") or Decimal(1)

        await safe_edit(query, "🔄 Fetching market data...")

        await send_market_data(
            chat_id=chat_id,
            context=context,
            provider=provider_str,
            type_filter=type_filter,
            volume=volume,
            is_auto=False,
        )

        clear_draft(context)
        await safe_edit(
            query,
            "✅ Market data sent above.",
            reply_markup=None,  # No keyboard – just exit
        )
        return ConversationHandler.END

    # Fallback for unknown actions
    await safe_edit(query, "❌ Unknown action.")
    return ConversationHandler.END
