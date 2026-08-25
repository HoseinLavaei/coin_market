"""
Sends market data messages using the Telegram API directly.
No global bot instance required.
"""

from telegram import Bot

from ..coins import build_prices_output, build_subscription_description
from ..environment import BROADCAST_BOT_TOKEN


async def send_to_subscription(sub, coins, orderbooks, updated_at):
    """
    Send a market data update to a subscription.
    Uses the Telegram Bot API directly with BROADCAST_BOT_TOKEN.
    """
    bot = Bot(token=BROADCAST_BOT_TOKEN)

    content = build_prices_output(coins, orderbooks, sub.provider, sub.type_filter, sub.volume)
    filter_desc = build_subscription_description(
        sub.provider,
        sub.type_filter,
        sub.volume,
        sub.repeat_interval,
    )
    timestamp = updated_at.strftime('%H:%M:%S')
    msg = (
        f"{content}\n\n"
        f"🔄 Auto-update ({filter_desc}, 🕒 updated at {timestamp})"
    )

    # ─── Split into chunks if needed ──────────────────────────
    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await bot.send_message(chat_id=sub.chat_id, text=msg[i:i + 4096])
    else:
        await bot.send_message(chat_id=sub.chat_id, text=msg)
