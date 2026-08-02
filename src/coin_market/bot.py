import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

from . import Quote, Coins, Base, OrderBooks
from .providers.aban_tether import AbanTetherProvider
from .providers.bitpin import BitpinProvider
from .providers.exir import ExirProvider
from .providers.nobitex import NobitexProvider
from .providers.okex import OkexProvider
from .providers.ompfinex import OmpfinexProvider
from .providers.ramzinex import RamzinexProvider
from .providers.tabdeal import TabdealProvider
from .providers.wallex import WallexProvider

# ─── Global cache ─────────────────────────────────────────────
_cached_coins: Coins = Coins()
_cached_orderbooks: OrderBooks = OrderBooks()
_cache_updated_at = datetime.now(ZoneInfo(os.getenv("TIMEZONE", "UTC")))

# ─── Environment variables ────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
INTERVAL = int(os.getenv("INTERVAL", "60"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))


# ─── Data fetching ────────────────────────────────────────────

async def fetch_all() -> tuple[Coins, OrderBooks]:
    """Fetch fresh OTC and order book data from all providers."""
    providers = [
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

    coins_out = Coins()
    books_out = OrderBooks()

    # OTC
    tasks = [p.get_otc(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Coins):
            r = r.to_timezone(TIMEZONE)
            for coin in r.coins.values():
                coins_out.upsert(coin)

    # Order books
    tasks = [p.get_orderbook(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, OrderBooks):
            r = r.to_timezone(TIMEZONE)
            for book in r.books.values():
                books_out.upsert(book)

    return coins_out, books_out


# ─── Cache update + broadcast ──────────────────────────────

async def update_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch fresh data, update cache, and broadcast to group."""
    global _cached_coins, _cached_orderbooks, _cache_updated_at

    try:
        coins, books = await fetch_all()
        _cached_coins = coins
        _cached_orderbooks = books
        _cache_updated_at = datetime.now(TIMEZONE)

        timestamp = _cache_updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated successfully.")

        if GROUP_ID:
            msg = (
                f"Market update ({timestamp})\n\n"
                f"{coins}\n\n"
                f"{books}"
            )
            await context.bot.send_message(chat_id=GROUP_ID, text=msg)

    except Exception as e:
        print(f"Cache update failed: {e}")


# ─── Command handlers ────────────────────────────────────────

async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the latest cached data (plain text)."""
    if update.message is None:
        return  # no message to reply to

    timestamp = _cache_updated_at.strftime('%H:%M:%S')
    msg = (
        f"Latest market data (updated at {timestamp})\n\n"
        f"OTC prices:\n{_cached_coins}\n\n"
        f"Order books:\n{_cached_orderbooks}"
    )

    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await update.message.reply_text(msg[i:i + 4096])
    else:
        await update.message.reply_text(msg)


# ─── Bot startup ─────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("prices", prices_command))

    job_queue = app.job_queue
    if job_queue is None:
        print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
        sys.exit(1)

    job_queue.run_repeating(update_cache, interval=INTERVAL, first=0)

    print(f"Bot started. Cache updates every {INTERVAL}s. Commands: /prices")
    print(f"Broadcasting to group: {GROUP_ID}")

    await app.initialize()
    await app.start()

    if app.updater is None:
        print("Error: Updater is not available.")
        sys.exit(1)

    await app.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        if app.updater:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
