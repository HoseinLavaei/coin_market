"""
Confirm selection handler.
Shows a summary of all selections and allows confirmation.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft
from .menus import (
    build_confirm_keyboard,
    CONFIRM,
)
from ...domain.value_objects import build_subscription_description


async def show_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display confirmation menu with subscription summary."""
    draft = get_draft(context)

    # Build summary using the existing function
    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None

    summary = build_subscription_description(
        provider_str,
        type_str,
        draft.get("volume"),
        draft.get("repeat_interval"),
    )

    # Add chat method to summary
    chat_method = draft.get("chat_method")
    if chat_method == "custom":
        chat_info = f"Chat ID: {draft.get('chat_id')}"
    elif chat_method == "key":
        chat_info = "Key-based activation"
    else:
        chat_info = "Not set"

    text = (
        "📋 **Confirm Subscription**\n\n"
        f"{summary}\n\n"
        f"📨 {chat_info}\n\n"
        "Review your selections and confirm:"
    )

    await safe_edit(query, text, reply_markup=build_confirm_keyboard())
    return CONFIRM


async def handle_confirm_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm (Next) – create the subscription."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    draft = get_draft(context)

    provider_str = ",".join(draft.get("providers", [])) if draft.get("providers") else None
    type_str = ",".join(draft.get("types", [])) if draft.get("types") else None

    # ─── Extract user info ──────────────────────────────────
    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    # ─── Create the subscription ────────────────────────────
    try:
        from ...infrastructure.repositories import (
            add_subscription,
            create_pending_subscription,
        )
        from ...services.subscription_scheduler import reload_subscriptions_immediate
        from ...environment import KEY_EXPIRY_SECONDS, TIMEZONE
        from datetime import datetime, timedelta
        import secrets

        chat_method = draft.get("chat_method")

        if chat_method == "custom":
            # Direct activation
            chat_id: int | None = draft.get("chat_id")
            if chat_id is None:
                await safe_edit(query, "❌ No chat ID set.")
                return ConversationHandler.END

            await add_subscription(
                chat_id=chat_id,
                user_id=user.id,
                provider=provider_str,
                type_filter=type_str,
                volume=draft.get("volume"),
                repeat_interval=draft.get("repeat_interval"),
            )
            await reload_subscriptions_immediate()

            await safe_edit(query, "✅ Subscription activated! First update sent.")
            return ConversationHandler.END

        else:
            # Key-based activation
            key = secrets.token_hex(4).upper()
            expires_at = datetime.now(TIMEZONE) + timedelta(seconds=KEY_EXPIRY_SECONDS)

            await create_pending_subscription(
                key=key,
                user_id=user.id,
                provider=provider_str,
                type_filter=type_str,
                volume=draft.get("volume"),
                repeat_interval=draft.get("repeat_interval"),
                expires_at=expires_at,
            )

            filter_desc = build_subscription_description(
                provider_str,
                type_str,
                draft.get("volume"),
                draft.get("repeat_interval"),
            )

            await safe_edit(
                query,
                f"✅ Subscription request created!\n\n"
                f"Filters: {filter_desc}\n"
                f"Repeat every: {draft.get('repeat_interval')}s\n\n"
                f"To activate, send this key in the chat where you want updates:\n"
                f"🔑 `{key}`\n\n"
                f"Use `/conf {key}` in that chat (valid for {KEY_EXPIRY_SECONDS} seconds).",
            )
            return ConversationHandler.END

    except Exception as e:
        await safe_edit(query, f"❌ Failed to create subscription: {e}")
        return ConversationHandler.END


async def handle_confirm_back(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle back button to return to chat selection."""
    from .chat_handler import show_chat
    return await show_chat(query, context)


async def handle_confirm_cancel(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancel button."""
    clear_draft(context)
    await safe_edit(query, "❌ Subscription cancelled.")
    return ConversationHandler.END


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm selection interactions."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM

    if data.startswith("confirm:"):
        action = data.split(":", 1)[1]

        if action == "next":
            return await handle_confirm_next(update, context)
        if action == "back":
            return await handle_confirm_back(query, context)
        if action == "cancel":
            return await handle_confirm_cancel(query, context)

    if data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    return CONFIRM
