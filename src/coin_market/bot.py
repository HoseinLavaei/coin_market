import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from . import Quote, Coins, Base, OrderBooks
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
from .db import (
    init_db, load_latest_snapshot, save_snapshot, close_db,
    add_subscription, get_subscriptions_for_chat, get_active_subscriptions,
    pause_subscriptions_for_chat, resume_subscriptions_for_chat, delete_subscriptions_for_chat
)
from .subscription import build_subscription_description
from .parsers import parse_prices_args
from .filters import filter_coins_by_provider, filter_orderbooks_by_provider
from .message_builder import build_prices_output

# ─── Usage message ─────────────────────────────────────────────
USAGE_MESSAGE = (
    "Usage:\n"
    "/prices [--provider NAME | provider=NAME]\n"
    "        [--type otc|p2p | type=otc|p2p]\n"
    "        [--volume NUM | volume=NUM]\n"
    "        [--repeat SEC | repeat=SEC]\n"
    "        [--stop | stop]              (pause all)\n"
    "        [--resume]                   (resume all)\n"
    "        [--delete]                   (delete all)\n"
    "        [--list]                     (list all)\n\n"
    "Valid providers: " + ", ".join([p.value for p in ProviderName])
)

# ─── Global cache ─────────────────────────────────────────────
_cached_coins: Coins = Coins()
_cached_orderbooks: OrderBooks = OrderBooks()
_cache_updated_at = datetime.now(ZoneInfo(os.getenv("TIMEZONE", "UTC")))

# ─── Environment variables ────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
INTERVAL = int(os.getenv("INTERVAL", "60"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "UTC"))


# ─── Data fetching ────────────────────────────────────────────

async def fetch_all() -> tuple[Coins, OrderBooks]:
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


# ─── Unified message builder and sender ─────────────────────

async def send_market_data(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    provider: ProviderName | None = None,
    type_filter: str | None = None,
    volume: float | None = None,
    is_auto: bool = False,
) -> None:
    filter_desc = build_subscription_description(
        provider.value if provider else None,
        type_filter,
        volume,
        None,
    )

    timestamp = _cache_updated_at.strftime('%H:%M:%S')

    if provider:
        coins = filter_coins_by_provider(_cached_coins, provider)
        books = filter_orderbooks_by_provider(_cached_orderbooks, provider)
    else:
        coins = _cached_coins
        books = _cached_orderbooks

    content = build_prices_output(coins, books, type_filter, volume)

    prefix = "Auto-update" if is_auto else "Market data"
    msg = f"{prefix} ({filter_desc}, updated at {timestamp})\n\n{content}"

    if len(msg) > 4096:
        for i in range(0, len(msg), 4096):
            await context.bot.send_message(chat_id=chat_id, text=msg[i:i + 4096])
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg)


# ─── Cache update + subscription broadcaster ──────────────

async def update_cache_and_broadcast(context: ContextTypes.DEFAULT_TYPE) -> None:
    global _cached_coins, _cached_orderbooks, _cache_updated_at

    try:
        coins, books = await fetch_all()
        _cached_coins = coins
        _cached_orderbooks = books
        _cache_updated_at = datetime.now(TIMEZONE)

        await save_snapshot(coins, books)

        timestamp = _cache_updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated and saved to DB.")

        subscriptions = await get_active_subscriptions()
        print(f"[{timestamp}] Sending updates to {len(subscriptions)} subscriptions")

        for sub in subscriptions:
            try:
                provider = ProviderName[sub.provider.upper()] if sub.provider else None
                await send_market_data(
                    chat_id=sub.chat_id,
                    context=context,
                    provider=provider,
                    type_filter=sub.type_filter,
                    volume=sub.volume,
                    is_auto=True,
                )
            except Exception as e:
                print(f"Failed to send to {sub.chat_id}: {e}")

    except Exception as e:
        print(f"Cache update failed: {e}")


# ─── Helper to extract chat_id and args ─────────────────────

def _get_chat_and_args(update: Update) -> tuple[int, list[str]] | None:
    """Return (chat_id, args) from a message or channel post, or None if invalid."""
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


# ─── Command handler helpers ────────────────────────────────

async def _handle_stop(update: Update, chat_id: int) -> None:
    target = update.effective_message
    if target is None:
        return
    count = await pause_subscriptions_for_chat(chat_id)
    if count > 0:
        await target.reply_text(f"Paused {count} subscription(s) for this chat. Use /prices resume to restart.")
    else:
        await target.reply_text("No active subscriptions to pause.")


async def _handle_resume(update: Update, chat_id: int) -> None:
    target = update.effective_message
    if target is None:
        return
    count = await resume_subscriptions_for_chat(chat_id)
    if count > 0:
        await target.reply_text(f"Resumed {count} paused subscription(s) for this chat.")
    else:
        await target.reply_text("No paused subscriptions to resume.")


async def _handle_delete(update: Update, chat_id: int) -> None:
    target = update.effective_message
    if target is None:
        return
    count = await delete_subscriptions_for_chat(chat_id)
    if count > 0:
        await target.reply_text(f"Deleted {count} subscription(s) for this chat.")
    else:
        await target.reply_text("No subscriptions to delete.")


async def _handle_list(update: Update, chat_id: int) -> None:
    target = update.effective_message
    if target is None:
        return
    subs = await get_subscriptions_for_chat(chat_id)

    if not subs:
        await target.reply_text("No subscriptions for this chat.")
        return

    lines = ["Your subscriptions:"]
    for sub in subs:
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        lines.append(f"  #{sub.id}: {desc} (status: {sub.status})")

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
    volume: float | None,
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

    # Send first update immediately
    await send_market_data(
        chat_id=chat_id,
        context=context,
        provider=provider,
        type_filter=type_filter,
        volume=volume,
        is_auto=True,
    )

    filter_desc = build_subscription_description(
        provider.value if provider else None,
        type_filter,
        volume,
        None,
    )
    await target.reply_text(
        f"Subscription #{sub.id} created. Auto-updates every {interval}s with filters: {filter_desc}. "
        "First update sent immediately.\n"
        "Commands: /prices stop (pause all), /prices resume, /prices delete, /prices list"
    )


async def _handle_one_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    provider: ProviderName | None,
    type_filter: str | None,
    volume: float | None,
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
    target = update.effective_message  # should be non‑None here

    # Special commands that don't need filter parsing
    special_handlers = {
        "stop": _handle_stop,
        "pause": _handle_stop,
        "resume": _handle_resume,
        "delete": _handle_delete,
        "list": _handle_list,
    }

    if args and args[0].lower() in special_handlers:
        await special_handlers[args[0].lower()](update, chat_id)
        return

    # Parse filters and volume
    try:
        provider, type_filter, volume, repeat_interval, stop_flag = parse_prices_args(args)
    except ValueError as e:
        if target is not None:
            await target.reply_text(f"Error: {e}\n\n{USAGE_MESSAGE}")
        return

    # Dispatch based on flags
    if stop_flag:
        await _handle_stop(update, chat_id)
    elif repeat_interval is not None:
        await _handle_watch(update, context, chat_id, provider, type_filter, volume, repeat_interval)
    else:
        await _handle_one_time(update, context, chat_id, provider, type_filter, volume)


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
            print(f"[{timestamp}] Loaded {len(_cached_coins.coins)} coins and {len(_cached_orderbooks.books)} orderbooks from DB.")
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

    job_queue.run_once(update_cache_and_broadcast, when=0)
    job_queue.run_repeating(update_cache_and_broadcast, interval=INTERVAL)

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