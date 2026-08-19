"""
Shared help texts for the presentation layer.
"""


def get_broadcast_help_text() -> str:
    """Return the help message for the broadcast bot."""
    return (
        "📡 **Broadcast Bot**\n\n"
        "This bot delivers live market data to your chat.\n\n"
        "**What you can do:**\n\n"
        "📊 **View Prices** – Get a one‑time snapshot of current market prices.\n"
        "   • Select which exchanges (providers) to include.\n"
        "   • Choose OTC, P2P, or both.\n"
        "   • Set a custom volume for price calculation.\n"
        "   • Then tap 'Fetch' to see the data.\n\n"
        "🔑 **Activate Subscription** – Start receiving automatic updates.\n"
        "   • You'll need a key from the Control Bot.\n"
        "   • Enter the 6‑digit key using the numeric keypad.\n"
        "   • Once activated, you'll receive updates at your chosen interval.\n\n"
        "❓ **Help** – This screen.\n\n"
        "**How to get a key:**\n"
        "Use the Control Bot to create a subscription. During setup, "
        "choose 'Get Key' instead of 'Custom Chat ID'.\n\n"
        "Then come back here, open the menu with /start or /menu, "
        "and choose 'Activate Subscription'.\n\n"
        "💡 **Tip:** The key is valid for a limited time, so activate it promptly."
    )
