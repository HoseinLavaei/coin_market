"""
Edit subscription handler – select a subscription to edit.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, SELECT_EDIT_SUB
from ...domain.value_objects import build_subscription_description
from ...infrastructure.repositories import get_subscriptions_for_user


async def edit_subscription_menu(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list of subscriptions to edit."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    if not subs:
        await safe_edit(query, "📭 You have no subscriptions to edit.")
        return ConversationHandler.END

    buttons = []
    for sub in subs:
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        status = "✅" if sub.status == "active" else "⏸️"
        buttons.append([
            InlineKeyboardButton(
                f"{status} #{sub.id}: {desc}",
                callback_data=f"edit_sel:{sub.id}"
            )
        ])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")])

    await safe_edit(
        query,
        "Select a subscription to edit:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECT_EDIT_SUB


async def edit_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle selection of a subscription to edit."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_EDIT_SUB

    if data == "edit_cancel":
        await safe_edit(query, "❌ Edit cancelled.")
        return ConversationHandler.END

    if not data.startswith("edit_sel:"):
        return SELECT_EDIT_SUB

    try:
        sub_id = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        await safe_edit(query, "❌ Invalid subscription ID.")
        return ConversationHandler.END

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    sub = next((s for s in subs if s.id == sub_id), None)
    if not sub:
        await safe_edit(query, "❌ Subscription not found.")
        return ConversationHandler.END

    # Populate draft with current values
    providers = sub.provider.split(",") if sub.provider else []
    types = sub.type_filter.split(",") if sub.type_filter else []

    draft = get_draft(context)
    draft["providers"] = providers
    draft["types"] = types
    draft["volume"] = sub.volume
    draft["repeat_interval"] = sub.repeat_interval
    draft["chat_method"] = "custom" if sub.chat_id else "key"
    draft["chat_id"] = sub.chat_id
    draft["edit_id"] = sub.id

    # Start the builder flow from provider selection
    from .selection_handlers import show_selection
    return await show_selection(query, context, "prov")
