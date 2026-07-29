import asyncio
import os
import sys
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, ContextTypes

from . import Quote, Coins, Base, Provider, OrderBooks
from .providers.aban_tether import AbanTetherProvider
from .providers.bitpin import BitpinProvider
from .providers.exir import ExirProvider
from .providers.nobitex import NobitexProvider
from .providers.ramzinex import RamzinexProvider
from .providers.wallex import WallexProvider
from .providers.tabdeal import TabdealProvider
from .providers.ompfinex import OmpfinexProvider
from .providers.okex import OkexProvider

# Global config variables (will be set in run_bot)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
INTERVAL = int(os.getenv("INTERVAL", "60"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))


async def get_tethers() -> tuple[Coins,OrderBooks]:
    providers: list[Provider] = [
        AbanTetherProvider(),
        BitpinProvider(),
        ExirProvider(),
        NobitexProvider(),
        RamzinexProvider(),
        WallexProvider(),
        TabdealProvider(),
        OmpfinexProvider(),
        OkexProvider(),
    ]

    quotes = [Quote.RLS]
    bases = [Base.USDT]
    output = (Coins(),OrderBooks())

    tasks_otc = [provider.get_otc(quotes, bases) for provider in providers]
    results_otc = await asyncio.gather(*tasks_otc, return_exceptions=True)
    coins_list:list[Coins] = results_otc
    coins_list = [coins.to_timezone(TIMEZONE) for coins in coins_list]
    for coins in coins_list:
        for coin in coins.coins.values():
            output[0].upsert(coin)

    tasks_orderbook = [provider.get_orderbook(quotes, bases) for provider in providers]
    results_orderbook = await asyncio.gather(*tasks_orderbook, return_exceptions=True)
    orderbooks_list:list[OrderBooks] = results_orderbook
    orderbooks_list = [orderbooks.to_timezone(TIMEZONE) for orderbooks in orderbooks_list]
    for orderbooks in orderbooks_list:
        for orderbook in orderbooks.books.values():
            output[1].upsert(orderbook)

    return output

async def broadcast_prices_job(context: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return

    # Fetch once and broadcast
    coins,orderbooks = await get_tethers()

    try:
        await context.bot.send_message(chat_id=GROUP_ID, text=coins.__str__())
        await context.bot.send_message(chat_id=GROUP_ID, text=orderbooks.__str__())
    except Exception as e:
        print(f"Failed to send to group {GROUP_ID}: {e}")


async def run_bot():
    global TELEGRAM_TOKEN, INTERVAL, GROUP_ID

    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable is not set.")
        sys.exit(1)

    if not GROUP_ID:
        print("Error: GROUP_ID environment variable is not set. Bot will not be able to send messages.")
        sys.exit(1)

    # =========================

    # Build the application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add job to broadcast prices periodically
    job_queue = application.job_queue
    if job_queue is None:
        print("Error: JobQueue is not available. Ensure 'python-telegram-bot[job-queue]' is installed.")
        sys.exit(1)

    job_queue.run_repeating(broadcast_prices_job, interval=INTERVAL, first=1)

    print(f"Bot is starting. Broadcasting to group {GROUP_ID} every {INTERVAL} seconds.")
    print("Listening for commands in private chats...")

    # Start the bot
    await application.initialize()
    await application.start()

    if application.updater is None:
        print("Error: Updater is not available.")
        sys.exit(1)

    await application.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        if application.updater:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
