"""
Broadcast bot command handlers.
"""

from ..coins import build_subscription_description
from ..db.repositories import (
    claim_pending_subscription,
    add_or_replace_subscription,
    delete_pending_subscription,
)


async def handle_start(update, context):
    """
    Handle /start command:
    - If a key is provided (e.g., /start 123456), activate subscription.
    - Otherwise, do nothing.
    """
    args = context.args
    if not args:
        return

    key = args[0].strip()
    if len(key) != 6 or not key.isdigit():
        message = update.effective_message
        if message:
            await message.reply_text("❌ Invalid key format. Please request a new one.")
        return

    message = update.effective_message
    if not message:
        return

    chat = update.effective_chat
    if not chat:
        await message.reply_text("❌ Could not determine chat.")
        return

    chat_id = chat.id

    # ─── Claim the pending subscription ──────────────────────
    data = await claim_pending_subscription(key, chat_id)
    if data is None:
        await message.reply_text(
            "❌ Invalid or expired key. Please request a new one from the Control Bot."
        )
        return

    try:
        # ─── Create/replace the subscription ──────────────────
        await add_or_replace_subscription(
            user_id=data["user_id"],
            chat_id=data["chat_id"],
            provider=data["provider"],
            type_filter=data["type_filter"],
            volume=data["volume"],
            repeat_interval=data["repeat_interval"],
        )
        await delete_pending_subscription(key)

        # ─── Confirm activation (no immediate update) ──────────
        filter_desc = build_subscription_description(
            data["provider"],
            data["type_filter"],
            data["volume"],
            data["repeat_interval"],
        )
        await message.reply_text(
            f"✅ Subscription activated!\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {data['repeat_interval']} minute(s)\n"
            f"The first update will be sent within the next minute."
        )

    except Exception as e:
        await message.reply_text(f"❌ Failed to create subscription: {e}")
