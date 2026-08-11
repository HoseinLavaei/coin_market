import asyncio
import signal
import sys
from datetime import datetime
from decimal import Decimal
from typing import cast

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, Job, JobQueue

from . import Quote, Coins, Base, OrderBooks
from .db import (
    init_db, load_latest_snapshot, save_snapshot, close_db,
    get_active_subscriptions, claim_pending_subscription,
    add_subscription, delete_pending_subscription
)
from .environment import TIMEZONE, BROADCAST_BOT_TOKEN, INTERVAL
from .message_builder import build_prices_output
from .parsers import parse_prices_args
from .provider_name import ProviderName
from .providers.aban_tether import AbanTetherProvider
from .providers.bitpin import BitpinProvider
from .providers.exir import ExirProvider
from .providers.nobitex import NobitexProvider
from .providers.okex import OkexProvider
from .providers.ompfinex import OmpfinexProvider
from .providers.ramzinex import RamzinexProvider
from .providers.tabdeal import TabdealProvider
from .providers.wallex import WallexProvider
from .subscription import build_subscription_description

# ─── Global cache ─────────────────────────────────────────────
_cached_coins: Coins = Coins()
_cached_orderbooks: OrderBooks = OrderBooks()
_cache_updated_at = datetime.now(TIMEZONE)

# ─── Subscription jobs ──────────────────────────────────────
_subscription_jobs: dict[int, Job] = {}


# ─── Data fetching ────────────────────────────────────────────

async def fetch_all() -> tuple[Coins, OrderBooks]:
    providers = [
        AbanTetherProvider(),
        BitpinProvider(),
        ExirProvider(),
        NobitexProvider(),
        OkexProvider(),
        OmpfinexProvider(),
        RamzinexProvider(),
        TabdealProvider(),
        WallexProvider(),
    ]

    quotes = [Quote.TMN]
    bases = [Base.USDT]

    coins_out = Coins()
    books_out = OrderBooks()

    # OTC
    tasks = [p.get_otc(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Coins):
            r = r.to_timezone()
            for coin in r.coins.values():
                coins_out.upsert(coin)

    # Order books
    tasks = [p.get_orderbook(quotes, bases) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, OrderBooks):
            r = r.to_timezone()
            for book in r.books.values():
                books_out.upsert(book)

    return coins_out, books_out


# ─── Unified message builder and sender ─────────────────────

async def send_market_data(
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        provider: ProviderName | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
        is_auto: bool = False,
) -> None:
    filter_desc = build_subscription_description(
        provider.value if provider else None,
        type_filter,
        volume,
        None,
    )

    timestamp = _cache_updated_at.strftime('%H:%M:%S')
    content = build_prices_output(_cached_coins, _cached_orderbooks, provider, type_filter, volume)

    prefix = "🔄 Auto-update" if is_auto else "📊 Market data"
    msg = f"{prefix} ({filter_desc}, 🕒 updated at {timestamp})\n\n{content}"

    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await context.bot.send_message(chat_id=chat_id, text=msg[i:i + 4096])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg)


# ─── Cache update ────────────────────────────────────────────

async def update_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _cached_coins, _cached_orderbooks, _cache_updated_at

    try:
        coins, books = await fetch_all()
        _cached_coins = coins
        _cached_orderbooks = books
        _cache_updated_at = datetime.now(TIMEZONE)

        await save_snapshot(coins, books)

        timestamp = _cache_updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated and saved to DB.")

        await reload_subscriptions(context)

    except Exception as e:
        print(f"Cache update failed: {e}")


# ─── Subscription job callback ──────────────────────────────

async def send_subscription_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    data = job.data
    if not isinstance(data, dict):
        return
    chat_id: int | None = data.get("chat_id")
    if chat_id is None:
        return
    provider_name: str | None = data.get("provider")
    provider = ProviderName[provider_name.upper()] if provider_name else None
    type_filter = data.get("type_filter")
    volume = data.get("volume")

    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=True,
    )


# ─── Manage subscription jobs ─────────────────────────────

def schedule_subscription_job(job_queue: JobQueue, sub) -> Job:
    data = {
        "chat_id": sub.chat_id,
        "provider": sub.provider,
        "type_filter": sub.type_filter,
        "volume": sub.volume,
    }
    job = job_queue.run_repeating(
        send_subscription_update,
        interval=sub.repeat_interval,
        first=sub.repeat_interval,
        data=data,
    )
    return job


async def load_and_schedule_all_subscriptions(job_queue: JobQueue, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _subscription_jobs
    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"Scheduled subscription #{sub.id} every {sub.repeat_interval}s")

        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        await send_market_data(
            chat_id=sub.chat_id,
            context=context,
            provider=provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )


async def reload_subscriptions(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _subscription_jobs
    for job in list(_subscription_jobs.values()):
        job.schedule_removal()
    _subscription_jobs.clear()
    await load_and_schedule_all_subscriptions(cast(JobQueue, context.job_queue), context)


# ─── Command handlers ────────────────────────────────────────

async def _handle_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await message.reply_text(f"❌ Error parsing filters: {e}\n\nUsage: /prices [--provider NAME] [--type otc|p2p] [--volume NUM]")
        return

    if repeat_interval is not None:
        await message.reply_text("ℹ️ --repeat is ignored for one-time /prices request. Use the control bot for subscriptions.")

    chat_id = effective_chat.id
    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=False,
    )


async def _handle_conf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    print(f"[Broadcast] Received /conf with key '{key}' from chat {chat_id}")

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
        job = schedule_subscription_job(job_queue, sub)
        _subscription_jobs[sub.id] = job

        provider = ProviderName[sub.provider.upper()] if sub.provider else None
        await send_market_data(
            chat_id=sub.chat_id,
            context=context,
            provider=provider,
            type_filter=sub.type_filter,
            volume=sub.volume,
            is_auto=True,
        )

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
        print(f"[Broadcast] Subscription activated for chat {chat_id} with key {key}")
    except Exception as e:
        await message.reply_text(f"❌ Failed to create subscription: {e}")
        print(f"[Broadcast] Error activating subscription: {e}")


async def _handle_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
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


# ─── Main handler ─────────────────────────────────────────────

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
        await _handle_prices(update, context)
    elif command == "conf":
        await _handle_conf(update, context)
    elif command == "help":
        await _handle_help(update, context)


# ─── Bot startup ─────────────────────────────────────────────

async def run_broadcast_bot():
    if not BROADCAST_BOT_TOKEN:
        print("Error: BROADCAST_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    print("Initializing database...")
    await init_db()

    print("Loading latest market data from database...")
    global _cached_coins, _cached_orderbooks, _cache_updated_at
    try:
        snapshot = await load_latest_snapshot()
        if snapshot:
            _cached_coins, _cached_orderbooks = snapshot
            _cache_updated_at = datetime.now(TIMEZONE)
            timestamp = _cache_updated_at.strftime('%H:%M:%S')
            print(f"[{timestamp}] Loaded {len(_cached_coins.coins)} coins and {len(_cached_orderbooks.books)} orderbooks from DB.")
        else:
            print("No previous data in database. Will fetch on first update.")
    except Exception as e:
        print(f"Warning: Could not load snapshot: {e}")

    app = ApplicationBuilder().token(BROADCAST_BOT_TOKEN).build()

    # Delete any existing webhook to ensure polling works
    try:
        await app.bot.delete_webhook()
        print("Webhook deleted (if any).")
    except Exception as e:
        print(f"Error deleting webhook: {e}")

    # Use filters.COMMAND to only catch messages that start with '/'
    app.add_handler(MessageHandler(filters.COMMAND, handle_command))

    job_queue = app.job_queue
    if job_queue is None:
        print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
        sys.exit(1)

    # Create a simple context-like object with the required job_queue attribute
    dummy_context = type('DummyContext', (), {'job_queue': job_queue, 'bot': None})()

    # Initial cache update and subscription load
    await update_cache(dummy_context)   # type: ignore[arg-type]

    # Schedule periodic cache updates
    job_queue.run_repeating(update_cache, interval=INTERVAL)

    print(f"Broadcast bot started. Cache updates every {INTERVAL}s.")
    print("Commands: /prices, /conf KEY, /help")

    await app.initialize()
    await app.start()

    if app.updater is None:
        print("Error: Updater is not available.")
        sys.exit(1)

    # Start polling with allowed_updates to ensure messages and channel posts are received
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