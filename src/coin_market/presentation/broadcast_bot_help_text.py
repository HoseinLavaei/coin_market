"""
Shared help texts for the presentation layer.
"""


def get_broadcast_help_text() -> str:
    """Return the help message for the broadcast bot."""
    return (
        "🤖 Broadcast Bot\n\n"
        "This bot broadcasts live market data (OTC & P2P) to your chat.\n\n"
        "Commands:\n"
        "  /prices [--provider NAME] [--type otc|p2p] [--volume NUM] – Show market data once.\n"
        "  /conf KEY – Activate a subscription using a key from the control bot.\n"
        "  /help – Show this message.\n\n"
        "To get a subscription key, use the control bot with /prices --repeat SEC."
    )