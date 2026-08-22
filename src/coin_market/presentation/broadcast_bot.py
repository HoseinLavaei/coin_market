"""
Broadcast bot – deep‑link activation only.
/start KEY activates a subscription.
"""

import asyncio
import signal
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler

from ..domain import build_subscription_description
from ..environment import BROADCAST_BOT_TOKEN, INTERVAL
from ..infrastructure import init_db, close_db
from ..infrastructure.repositories import claim_pending_subscription, add_subscription, delete_pending_subscription
from ..services import (
    update_cache,
    load_cache_from_db,
    set_job_queue,
    set_broadcast_bot,
    schedule_subscription_job,
)
from ..services.subscription_scheduler import get_job_queue, send_market_data


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command:
    - If a key is provided (e.g., /start 123456), activate subscription.
    - Otherwise, do nothing.
    """
    args = context.args
    if not args:
        return ConversationHandler.END

    key = args[0].strip()
    if len(key) != 6 or not key.isdigit():
        message = update.effective_message
        if message:
            await message.reply_text("❌ Invalid key format. Please request a new one.")
        return ConversationHandler.END

    message = update.effective_message
    if not message:
        return ConversationHandler.END

    chat = update.effective_chat
    if not chat:
        await message.reply_text("❌ Could not determine chat.")
        return ConversationHandler.END

    chat_id = chat.id

    data = await claim_pending_subscription(key, chat_id)
    if data is None:
        await message.reply_text(
            "❌ Invalid or expired key. Please request a new one from the Control Bot."
        )
        return ConversationHandler.END

    try:
        sub = await add_subscription(
            chat_id=data["chat_id"],
            user_id=data["user_id"],
            provider=data["provider"],
            type_filter=data["type_filter"],
            volume=data["volume"],
            repeat_interval=data["repeat_interval"],
        )
        await delete_pending_subscription(key)

        job_queue = get_job_queue()
        if job_queue is None:
            await message.reply_text("❌ Job queue not available.")
            return ConversationHandler.END

        schedule_subscription_job(job_queue, sub)

        # ─── Send first update ──────────────────────────────
        try:
            await send_market_data(
                chat_id=sub.chat_id,
                context=context,
                provider=sub.provider,
                type_filter=sub.type_filter,
                volume=sub.volume,
                is_auto=True,
            )
        except Exception as e:
            print(f"⚠️ First update failed for subscription #{sub.id}: {e}")

        filter_desc = build_subscription_description(
            data["provider"],
            data["type_filter"],
            data["volume"],
            data["repeat_interval"],
        )
        await message.reply_text(
            f"✅ Subscription activated!\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {data['repeat_interval']}s\n"
            f"You will receive updates here."
        )
        return ConversationHandler.END

    except Exception as e:
        await message.reply_text(f"❌ Failed to create subscription: {e}")
        return ConversationHandler.END


async def run_broadcast_bot():
    """
    Main entry point for the broadcast bot.
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

            # ─── Only /start handler ──────────────────────────
            app.add_handler(CommandHandler("start", handle_start))

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
            print("Use /start KEY to activate a subscription.")

            await app.initialize()
            await app.start()

            if app.updater is None:
                print("Error: Updater is not available.")
                sys.exit(1)

            await app.updater.start_polling(
                allowed_updates=["message", "channel_post"]
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