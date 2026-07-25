import asyncio
import os
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import AbanTetherProvider, BitpinProvider, ExirProvider, NobitexProvider, RamzinexProvider, \
    WallexProvider, Quote, Coins

# Global set to store all user chat IDs
subscribed_users = set()

# Global config variables (will be set in run_bot)
TELEGRAM_TOKEN = None
INTERVAL = 60

async def get_tethers() -> Coins:
    providers = [AbanTetherProvider(), BitpinProvider(), ExirProvider(), NobitexProvider(), RamzinexProvider(),
                 WallexProvider()]

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
            coins.upsert(coin)
    return coins

async def send_prices_to_user(bot, user_id: int):
    """Fetch prices and send to a specific user."""
    coins = await get_tethers()
    full_message = f"{'#' * 50}\n{coins}\n"
    try:
        await bot.send_message(chat_id=user_id, text=full_message)
    except Exception as e:
        print(f"Failed to send to {user_id}: {e}")

async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    msg = update.message
    if not msg:
        return

    user_id = chat.id
    subscribed_users.add(user_id)
    await msg.reply_text(
        f"You're subscribed! You'll receive USDT price updates every {INTERVAL} seconds."
    )

    # Send the current prices immediately
    await send_prices_to_user(_context.bot, user_id)

async def broadcast_prices(context: ContextTypes.DEFAULT_TYPE):
    if not subscribed_users:
        return

    # We don't need to fetch inside the loop – fetch once and reuse
    coins = await get_tethers()
    full_message = f"{'#' * 50}\n{coins}\n"

    for user_id in list(subscribed_users):
        try:
            await context.bot.send_message(chat_id=user_id, text=full_message)
        except Exception as e:
            print(f"Failed to send to {user_id}: {e}")

def run_bot():
    global TELEGRAM_TOKEN, INTERVAL
    
    # ===== CONFIGURATION =====
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    try:
        INTERVAL = int(os.getenv("INTERVAL", "60"))
    except ValueError:
        print("Warning: INTERVAL env var is not a valid integer. Using default of 60 seconds.")
        INTERVAL = 60

    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable is not set.")
        sys.exit(1)
    # =========================

    # Create the Application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handler for /start
    app.add_handler(CommandHandler("start", start))

    # Schedule the broadcast to run every INTERVAL seconds
    job_queue = app.job_queue
    job_queue.run_repeating(broadcast_prices, interval=INTERVAL, first=0)

    # Start the bot (this blocks until you stop it)
    print("Bot is running. Send /start to subscribe.")
    app.run_polling()
