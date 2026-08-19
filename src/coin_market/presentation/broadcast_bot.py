"""
Broadcast bot – handles one‑time price requests, subscription activation via key,
and runs the main polling loop. It also stores the bot instance for immediate updates.
"""

import asyncio
import signal
import sys

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

from .inline_keyboard import (
    broadcast_conversation,
    show_broadcast_main_menu,
)
from ..environment import BROADCAST_BOT_TOKEN, INTERVAL
from ..infrastructure import init_db, close_db
from ..services import (
    update_cache, load_cache_from_db,
    set_job_queue,
    set_broadcast_bot,
)


async def handle_start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start and /menu commands explicitly.
    Works for both messages and channel posts.
    """
    # Determine the command text
    if update.message:
        text = update.message.text
    elif update.channel_post:
        text = update.channel_post.text
    else:
        return
    if not text:
        return
    parts = text.split()
    if not parts:
        return
    cmd = parts[0].lower()
    if cmd not in ('/start', '/menu'):
        return
    # Forward to the menu display
    await show_broadcast_main_menu(update, context)


async def run_broadcast_bot():
    """
    Main entry point for the broadcast bot.
    Initializes the database, loads cache, sets up the application,
    and starts polling. Restarts automatically if it crashes.
    """
    while True:
        try:
            if not BROADCAST_BOT_TOKEN:
                print("Error: BROADCAST_BOT_TOKEN environment variable not set.")
                sys.exit(1)

            print("Initializing database...")
            await init_db()

            print("Loading latest market data from database...")
            await load_cache_from_db()

            app = ApplicationBuilder().token(BROADCAST_BOT_TOKEN).build()

            # ─── Dedicated handler for /start and /menu (no regex, just command check) ──
            app.add_handler(MessageHandler(
                filters.COMMAND & (filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST),
                handle_start_menu
            ))

            # ─── Inline menu conversation ─────────────────────────────────
            app.add_handler(broadcast_conversation)

            job_queue = app.job_queue
            if job_queue is None:
                print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
                sys.exit(1)

            set_job_queue(job_queue)
            set_broadcast_bot(app.bot)

            dummy_context = type('DummyContext', (), {
                'job_queue': job_queue,
                'bot': app.bot,
            })()

            await update_cache(dummy_context)
            job_queue.run_repeating(update_cache, interval=INTERVAL)

            print(f"Broadcast bot started. Cache updates every {INTERVAL}s.")
            print("Commands: /prices, /conf KEY, /help")

            await app.initialize()
            await app.start()

            if app.updater is None:
                print("Error: Updater is not available.")
                sys.exit(1)

            await app.updater.start_polling(
                allowed_updates=["message", "channel_post", "callback_query"]
            )

            shutdown_event = asyncio.Event()
            loop = asyncio.get_running_loop()

            def signal_handler():
                print("Received termination signal, shutting down broadcast bot...")
                shutdown_event.set()

            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)

            await shutdown_event.wait()

            print("EXITING broadcast bot...")
            if app.updater:
                await app.updater.stop()
            await app.stop()
            await close_db()
            await app.shutdown()
            break

        except Exception as e:
            print(f"❌ Broadcast bot crashed: {e}")
            import traceback
            traceback.print_exc()
            print("🔄 Restarting broadcast bot in 5 seconds...")
            await asyncio.sleep(5)
