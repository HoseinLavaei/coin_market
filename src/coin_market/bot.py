import asyncio
import os
import sys

from telegram import Bot

from . import AbanTetherProvider, BitpinProvider, ExirProvider, NobitexProvider, RamzinexProvider, \
    WallexProvider, Quote, Coins
from .db import init_db, save_coins

# Global config variables (will be set in run_bot)
TELEGRAM_TOKEN = None
INTERVAL = 60
GROUP_ID = None


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


async def broadcast_prices(bot):
    if not GROUP_ID:
        return

    # Fetch once and broadcast
    coins = await get_tethers()
    full_message = f"{'#' * 50}\n{coins}\n"

    # Save to database
    try:
        await save_coins(coins)
    except Exception as e:
        print(f"Failed to save to database: {e}")

    try:
        await bot.send_message(chat_id=GROUP_ID, text=full_message)
    except Exception as e:
        print(f"Failed to send to group {GROUP_ID}: {e}")


async def run_bot():
    global TELEGRAM_TOKEN, INTERVAL, GROUP_ID

    # ===== CONFIGURATION =====
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    GROUP_ID = os.getenv("GROUP_ID")

    try:
        INTERVAL = int(os.getenv("INTERVAL", "60"))
    except ValueError:
        print("Warning: INTERVAL env var is not a valid integer. Using default of 60 seconds.")
        INTERVAL = 60

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

    bot = Bot(token=TELEGRAM_TOKEN)

    print(f"Bot is starting. Broadcasting to group {GROUP_ID} every {INTERVAL} seconds.")

    while True:
        start_time = asyncio.get_event_loop().time()
        await broadcast_prices(bot)

        elapsed = asyncio.get_event_loop().time() - start_time
        wait_time = max(0, INTERVAL - elapsed)
        await asyncio.sleep(wait_time)
