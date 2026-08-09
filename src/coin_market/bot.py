import asyncio
import sys
from datetime import datetime
from decimal import Decimal

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, Job

from . import Quote, Coins, Base, OrderBooks
from .db import (
    init_db, load_latest_snapshot, save_snapshot, close_db,
    add_subscription, get_subscriptions_for_chat, get_active_subscriptions,
    pause_subscriptions_for_chat, resume_subscriptions_for_chat, delete_subscriptions_for_chat
)
from .environment import TIMEZONE, TELEGRAM_TOKEN, INTERVAL
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

# ─── Usage message ─────────────────────────────────────────────
USAGE_MESSAGE = (
        "📖 Usage:\n"
        "/prices [options]\n\n"
        "Options:\n"
        "  🔹 --provider NAME   | provider=NAME   (filter by provider)\n"
        "  🔹 --type otc|p2p    | type=otc|p2p    (show only OTC or P2P)\n"
        "  🔹 --volume NUM      | volume=NUM      (volume for VWAP calculation)\n"
        "  🔹 --repeat SEC      | repeat=SEC      (start auto-updates every SEC seconds)\n"
        "  🔹 --stop            | stop            (pause all subscriptions)\n"
        "  🔹 --resume          | resume          (resume all paused subscriptions)\n"
        "  🔹 --delete          | delete          (delete all subscriptions)\n"
        "  🔹 --list            | list            (list your subscriptions)\n\n"
        "Valid providers: " + ", ".join([p.value for p in ProviderName])
)

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

    # No filtering here – pass the full cache and let build_prices_output handle it
    content = build_prices_output(_cached_coins, _cached_orderbooks, provider, type_filter, volume)

    prefix = "🔄 Auto-update" if is_auto else "📊 Market data"
    msg = f"{prefix} ({filter_desc}, 🕒 updated at {timestamp})\n\n{content}"

    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await context.bot.send_message(chat_id=chat_id, text=msg[i:i + 4096])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg)


# ─── Cache update (no broadcasting) ─────────────────────────

async def update_cache(_context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch fresh data, update cache, and save snapshot to DB."""
    global _cached_coins, _cached_orderbooks, _cache_updated_at

    try:
        coins, books = await fetch_all()
        _cached_coins = coins
        _cached_orderbooks = books
        _cache_updated_at = datetime.now(TIMEZONE)

        await save_snapshot(coins, books)

        timestamp = _cache_updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated and saved to DB.")

    except Exception as e:
        print(f"Cache update failed: {e}")


# ─── Subscription job callback ──────────────────────────────

async def send_subscription_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by a subscription job to send an update."""
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

def schedule_subscription_job(job_queue, sub) -> Job:
    """Schedule a repeating job for a subscription. Returns the Job."""
    data = {
        "chat_id": sub.chat_id,
        "provider": sub.provider,
        "type_filter": sub.type_filter,
        "volume": sub.volume,
    }
    job_queue.run_once(send_subscription_update, when=0, data=data)

    job = job_queue.run_repeating(
        send_subscription_update,
        interval=sub.repeat_interval,
        first=0,
        data=data,
    )
    return job


def remove_jobs_for_chat(chat_id: int) -> None:
    """Remove all subscription jobs for a given chat_id."""
    global _subscription_jobs
    to_remove = []
    for sid, job in _subscription_jobs.items():
        data = job.data
        if isinstance(data, dict) and data.get("chat_id") == chat_id:
            to_remove.append(sid)
    for sid in to_remove:
        job = _subscription_jobs.pop(sid, None)
        if job:
            job.schedule_removal()


async def load_and_schedule_all_subscriptions(job_queue) -> None:
    """Load all active subscriptions from DB and schedule jobs."""
    global _subscription_jobs
    subs = await get_active_subscriptions()
    for sub in subs:
        if sub.repeat_interval is None:
            continue
        job = schedule_subscription_job(job_queue, sub)
        _subscription_jobs[sub.id] = job
        print(f"Scheduled subscription #{sub.id} every {sub.repeat_interval}s")


# ─── Command handler helpers ────────────────────────────────

async def _handle_stop(update: Update, _context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    global _subscription_jobs
    target = update.effective_message
    if target is None:
        return

    count = await pause_subscriptions_for_chat(chat_id)

    if count > 0:
        remove_jobs_for_chat(chat_id)
        await target.reply_text(f"⏸️ Paused {count} subscription(s) for this chat. Use /prices resume to restart.")
    else:
        await target.reply_text("ℹ️ No active subscriptions to pause.")


async def _handle_resume(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    global _subscription_jobs
    target = update.effective_message
    if target is None:
        return

    count = await resume_subscriptions_for_chat(chat_id)

    if count > 0:
        subs = await get_subscriptions_for_chat(chat_id)
        job_queue = context.job_queue
        if job_queue is None:
            await target.reply_text("❌ Job queue not available.")
            return
        for sub in subs:
            if sub.status == "active" and sub.repeat_interval is not None:
                job = schedule_subscription_job(job_queue, sub)
                _subscription_jobs[sub.id] = job
        await target.reply_text(f"▶️ Resumed {count} paused subscription(s) for this chat.")
    else:
        await target.reply_text("ℹ️ No paused subscriptions to resume.")


async def _handle_delete(update: Update, _context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    global _subscription_jobs
    target = update.effective_message
    if target is None:
        return

    count = await delete_subscriptions_for_chat(chat_id)

    if count > 0:
        remove_jobs_for_chat(chat_id)
        await target.reply_text(f"🗑️ Deleted {count} subscription(s) for this chat.")
    else:
        await target.reply_text("ℹ️ No subscriptions to delete.")


async def _handle_list(update: Update, chat_id: int) -> None:
    target = update.effective_message
    if target is None:
        return
    subs = await get_subscriptions_for_chat(chat_id)

    if not subs:
        await target.reply_text("📭 No subscriptions for this chat.")
        return

    lines = ["📋 Your subscriptions:"]
    for sub in subs:
        status_emoji = "✅" if sub.status == "active" else "⏸️"
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        lines.append(f"  {status_emoji} #{sub.id}: {desc} (status: {sub.status})")

    msg = "\n".join(lines)
    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await target.reply_text(msg[i:i + 4096])
    else:
        await target.reply_text(msg)


async def _handle_watch(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        provider: ProviderName | None,
        type_filter: str | None,
        volume: Decimal | None,
        interval: int,
) -> None:
    target = update.effective_message
    if target is None:
        return

    sub = await add_subscription(
        chat_id=chat_id,
        provider=provider.value if provider else None,
        type_filter=type_filter,
        volume=volume,
        repeat_interval=interval,
    )

    job_queue = context.job_queue
    if job_queue is None:
        await target.reply_text("❌ Job queue not available.")
        return
    job = schedule_subscription_job(job_queue, sub)
    _subscription_jobs[sub.id] = job

    filter_desc = build_subscription_description(
        provider.value if provider else None,
        type_filter,
        volume,
        None,
    )
    await target.reply_text(
        f"✅ Subscription #{sub.id} created. Auto-updates every {interval}s with filters: {filter_desc}.\n"
        "Commands: /prices stop (pause all), /prices resume, /prices delete, /prices list"
    )


async def _handle_one_time(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        provider: ProviderName | None,
        type_filter: str | None,
        volume: Decimal | None,
) -> None:
    target = update.effective_message
    if target is None:
        return
    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=False,
    )


# ─── Main command handler ────────────────────────────────────

async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /prices commands (works in private, groups, channels)."""
    extracted = _get_chat_and_args(update)
    if extracted is None:
        return

    chat_id, args = extracted
    target = update.effective_message

    special_handlers = {
        "stop": _handle_stop,
        "pause": _handle_stop,
        "resume": _handle_resume,
        "delete": _handle_delete,
        "list": _handle_list,
    }

    if args and args[0].lower() in special_handlers:
        await special_handlers[args[0].lower()](update, context, chat_id)
        return

    try:
        provider, type_filter, volume, repeat_interval, stop_flag = parse_prices_args(args)
    except ValueError as e:
        if target is not None:
            await target.reply_text(f"❌ Error: {e}\n\n{USAGE_MESSAGE}")
        return

    if stop_flag:
        await _handle_stop(update, context, chat_id)
    elif repeat_interval is not None:
        await _handle_watch(update, context, chat_id, provider, type_filter, volume, repeat_interval)
    else:
        await _handle_one_time(update, context, chat_id, provider, type_filter, volume)


# ─── Helper to extract chat_id and args ─────────────────────

def _get_chat_and_args(update: Update) -> tuple[int, list[str]] | None:
    msg = update.effective_message
    if msg is None:
        return None
    text = msg.text
    if not text or not text.startswith('/prices'):
        return None
    args = text.split()[1:]
    chat = update.effective_chat
    if chat is None:
        return None
    return chat.id, args


# ─── Bot startup ─────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
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
            print(
                f"[{timestamp}] Loaded {len(_cached_coins.coins)} coins and {len(_cached_orderbooks.books)} orderbooks from DB.")
        else:
            print("No previous data in database. Will fetch on first update.")
    except Exception as e:
        print(f"Warning: Could not load snapshot: {e}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, prices_command))

    job_queue = app.job_queue
    if job_queue is None:
        print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
        sys.exit(1)

    job_queue.run_once(update_cache, when=0)
    job_queue.run_repeating(update_cache, interval=INTERVAL)

    await load_and_schedule_all_subscriptions(job_queue)

    print(f"Bot started. Cache updates every {INTERVAL}s.")
    print("Commands: /prices [--provider] [--type] [--volume] [--repeat] [--stop] [--resume] [--delete] [--list]")

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
        await close_db()
        await app.shutdown()
