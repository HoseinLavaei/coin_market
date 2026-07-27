import asyncio
import os
import sys
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from . import Quote, Coins
from .providers.aban_tether import AbanTetherOTCProvider
from .providers.bitpin import BitpinOTCProvider, BitpinP2PProvider
from .providers.exir import ExirP2PProvider
from .providers.nobitex import NobitexOTCProvider, NobitexP2PProvider
from .providers.ramzinex import RamzinexOTCProvider, RamzinexP2PProvider
from .providers.wallex import WallexOTCProvider, WallexP2PProvider
from .db import init_db, save_coins, get_history

# Global config variables (will be set in run_bot)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
INTERVAL = int(os.getenv("INTERVAL", "60"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))


async def get_tethers() -> Coins:
    providers = [
        AbanTetherOTCProvider(),
        BitpinOTCProvider(), BitpinP2PProvider(),
        ExirP2PProvider(),
        NobitexOTCProvider(), NobitexP2PProvider(),
        RamzinexOTCProvider(), RamzinexP2PProvider(),
        WallexOTCProvider(), WallexP2PProvider()
    ]

    tasks = [provider.fetch(Quote.RLS) for provider in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    coins = Coins()
    for i, provider_coins in enumerate(results):
        provider = providers[i]
        if isinstance(provider_coins, Exception):
            print(f"Error fetching from {provider.provider_name}: {provider_coins}")
            continue

        coin = provider_coins.get(provider.provider_name, Quote.RLS, "USDT")
        if coin:
            coins.upsert(coin.to_timezone(TIMEZONE))
    return coins


async def broadcast_prices_job(context: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return

    # Fetch once and broadcast
    coins = await get_tethers()

    # Save to database
    try:
        await save_coins(coins)
    except Exception as e:
        print(f"Failed to save to database: {e}")

    try:
        await context.bot.send_message(chat_id=GROUP_ID, text=coins.__str__())
    except Exception as e:
        print(f"Failed to send to group {GROUP_ID}: {e}")


async def history_command(update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    try:
        n = int(context.args[0]) if context.args else 1
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /history <number>")
        return

    history_coins = await get_history(n * 12, TIMEZONE)
    if not history_coins:
        await update.message.reply_text("No history found.")
        return

    message = "History of coin prices:\n"
    for coin in history_coins:
        message += f"{coin}\n"

    # Telegram limit 4096
    for i in range(0, len(message), 4000):
        await update.message.reply_text(message[i:i + 4000])


async def run_bot():
    global TELEGRAM_TOKEN, INTERVAL, GROUP_ID

    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable is not set.")
        sys.exit(1)

    if not GROUP_ID:
        print("Error: GROUP_ID environment variable is not set. Bot will not be able to send messages.")
        sys.exit(1)

    # Initialize Database
    print("Initializing database...")
    await init_db()

    # =========================

    # Build the application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("history", history_command))

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
