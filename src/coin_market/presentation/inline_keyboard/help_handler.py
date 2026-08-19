"""
Help handler – displays information about the bot.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit


async def show_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Display help information about the Control Bot.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    help_text = (
        "🤖 **Control Bot – Help**\n\n"
        "This bot helps you create and manage market data subscriptions.\n\n"
        "**Available actions:**\n\n"
        "📊 **New Subscription** – Create a new subscription with filters:\n"
        "   • Providers: Select one or more exchanges\n"
        "   • Type: OTC, P2P, or both\n"
        "   • Volume: Customize the trading volume\n"
        "   • Interval: Set how often to receive updates\n"
        "   • Delivery: Send to this chat (Custom Chat ID) or generate a key for later activation\n\n"
        "📋 **My Subscriptions** – View all your active and paused subscriptions\n\n"
        "⏸️ **Stop Subscription** – Pause one or more active subscriptions\n\n"
        "▶️ **Resume Subscription** – Resume one or more paused subscriptions\n\n"
        "✏️ **Edit Subscription** – Modify the filters of an existing subscription\n\n"
        "🗑️ **Delete Subscription** – Permanently remove one or more subscriptions\n\n"
        "💡 **Tips:**\n"
        "• To receive updates in another chat, use the **Get Key** option during setup\n"
        "• Send the key to the Broadcast Bot in the desired chat using `/conf KEY`\n"
        "• Use `/start` or `/menu` to return to the main menu at any time\n\n"
        "❓ Need more help? Contact support."
    )

    await safe_edit(query, help_text, parse_mode="Markdown")
    return ConversationHandler.END
