"""
Broadcast bot command handlers.
"""

from telegram import Update
from telegram.ext import ContextTypes

from ..coins import build_subscription_description
from ..db import claim_subscription_by_key


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    data = await claim_subscription_by_key(key, chat_id)
    if data is None:
        await message.reply_text(
            "❌ Invalid or expired key. Please request a new one from the Control Bot."
        )
        return

    filter_desc = build_subscription_description(
        data["volume"],
        data["repeat_interval"],
    )
    await message.reply_text(
        f"✅ Subscription activated!\n"
        f"Filters: {filter_desc}\n"
        f"Repeat every: {data['repeat_interval']} minute(s)\n"
        f"The first update will be sent within the next minute."
    )
