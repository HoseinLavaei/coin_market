import asyncio
import signal
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from .parsers import parse_prices_args
from ..domain import ProviderName
from ..environment import BROADCAST_BOT_TOKEN, INTERVAL
from ..infrastructure import init_db, close_db
from ..infrastructure.repositories import claim_pending_subscription, add_subscription, delete_pending_subscription
from ..services import (
    update_cache, load_cache_from_db,
    schedule_subscription_job,
    send_market_data,
    set_job_queue,
)


# ─── Command Handlers ──────────────────────────────────────

async def handle_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    effective_chat = update.effective_chat
    if effective_chat is None:
        await message.reply_text("❌ Could not determine chat. Please try again.")
        return
    args = context.args or []
    try:
        provider, type_filter, volume, repeat_interval, stop_flag = parse_prices_args(args)
    except ValueError as e:
        await message.reply_text(
            f"❌ Error parsing filters: {e}\n\nUsage: /prices [--provider NAME] [--type otc|p2p] [--volume NUM]")
        return
    if repeat_interval is not None:
        await message.reply_text(
            "ℹ️ --repeat is ignored for one-time /prices request. Use the control bot for subscriptions.")
    chat_id = effective_chat.id
    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=False,
    )


async def handle_conf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    effective_chat = update.effective_chat
    if effective_chat is None:
        await message.reply_text("❌ Could not determine chat. Please try again.")
        return
    args = context.args or []
    if not args:
        await message.reply_text("❌ Please provide the key: `/conf KEY`")
        return
    key = args[0].strip()
    chat_id = effective_chat.id

    data = await claim_pending_subscription(key, chat_id)
    if data is None:
        await message.reply_text("❌ Invalid or expired key. Please request a new one.")
        return

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
        job_queue = context.job_queue
        if job_queue is None:
            await message.reply_text("❌ Job queue not available.")
            return
        schedule_subscription_job(job_queue, sub)
        # store job globally if needed (we can rely on the scheduler's internal dict)
        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        await send_market_data(
            chat_id=sub.chat_id,
            context=context,
            provider=provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )
        from ..domain.value_objects import build_subscription_description
        filter_desc = build_subscription_description(
            data["provider"],
            data["type_filter"],
            data["volume"],
            None,
        )
        await message.reply_text(
            f"✅ Subscription activated!\n"
            f"Filters: {filter_desc}\n"
            f"Repeat every: {data['repeat_interval']}s\n"
            f"You will receive updates here."
        )
    except Exception as e:
        await message.reply_text(f"❌ Failed to create subscription: {e}")


async def handle_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "🤖 Broadcast Bot\n\n"
        "This bot broadcasts live market data (OTC & P2P) to your chat.\n\n"
        "Commands:\n"
        "  /prices [--provider NAME] [--type otc|p2p] [--volume NUM] – Show market data once.\n"
        "  /conf KEY – Activate a subscription using a key from the control bot.\n"
        "  /help – Show this message.\n\n"
        "To get a subscription key, use the control bot with /prices --repeat SEC."
    )


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    command = parts[0].lower()
    if not command.startswith('/'):
        return
    command = command[1:]
    context.args = parts[1:] if len(parts) > 1 else []
    if command == "prices":
        await handle_prices(update, context)
    elif command == "conf":
        await handle_conf(update, context)
    elif command == "help":
        await handle_help(update, context)


# ─── Bot Lifecycle ──────────────────────────────────────────


async def run_broadcast_bot():
    if not BROADCAST_BOT_TOKEN:
        print("Error: BROADCAST_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    print("Initializing database...")
    await init_db()

    print("Loading latest market data from database...")
    await load_cache_from_db()

    app = ApplicationBuilder().token(BROADCAST_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.COMMAND, handle_command))

    job_queue = app.job_queue
    if job_queue is None:
        print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
        sys.exit(1)

    # Store the job queue globally so other modules can trigger reloads
    set_job_queue(job_queue)   # <--- NEW

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

    await app.updater.start_polling(allowed_updates=["message", "channel_post"])

    print("EXITING broadcast bot...")
    if app.updater:
        await app.updater.stop()
    await app.stop()
    await close_db()
    await app.shutdown()