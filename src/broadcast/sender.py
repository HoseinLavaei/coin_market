"""
Sends market data messages using the Telegram API directly.
No global bot instance required.
"""

from telegram import Bot
from telegram.request import HTTPXRequest

from ..coins import build_prices_output, build_subscription_description
from ..coins.models import Coins, OrderBooks
from ..environment import BROADCAST_BOT_TOKEN
from ..subscription_types import SubscriptionData


async def send_to_subscription(
        sub: SubscriptionData,
        coins: Coins,
        orderbooks: OrderBooks,
) -> None:
    """
    Send a market data update to a subscription.
    Uses the Telegram Bot API directly with BROADCAST_BOT_TOKEN.
    """
    if sub.chat_id is None:
        return

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    bot = Bot(token=BROADCAST_BOT_TOKEN, request=request)

    content = build_prices_output(coins, orderbooks, sub.provider, sub.type_filter, sub.volume)
    filter_desc = build_subscription_description(volume=sub.volume, repeat_interval=sub.repeat_interval, )
    msg = f"{content}\n\n({filter_desc})"

    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await bot.send_message(chat_id=sub.chat_id, text=msg[i:i + 4096])
    else:
        await bot.send_message(chat_id=sub.chat_id, text=msg)
