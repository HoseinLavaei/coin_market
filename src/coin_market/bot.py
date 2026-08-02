import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

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
from .db import init_db, load_latest_snapshot, save_snapshot, close_db

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
    """Fetch fresh data, update cache, save to database, and broadcast to group."""
    global _cached_coins, _cached_orderbooks, _cache_updated_at

    try:
        coins, books = await fetch_all()
        _cached_coins = coins
        _cached_orderbooks = books
        _cache_updated_at = datetime.now(TIMEZONE)

        # Save to database
        await save_snapshot(coins, books)

        timestamp = _cache_updated_at.strftime('%H:%M:%S')
        print(f"[{timestamp}] Cache updated successfully and saved to DB.")

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

def parse_price_filters(args: list[str]) -> tuple[ProviderName | None, str | None, float | None]:
    """Parse command arguments to extract provider, type, and volume filters.
    
    Raises ValueError if arguments are invalid.
    """
    provider_filter: ProviderName | None = None
    type_filter: str | None = None
    volume_filter: float | None = None

    valid_providers = {p.name.lower(): p for p in ProviderName}
    valid_types = {"otc", "p2p"}

    for arg in args:
        arg_lower = arg.lower()
        if arg_lower in valid_providers:
            provider_filter = valid_providers[arg_lower]
        elif arg_lower in valid_types:
            type_filter = arg_lower.upper()
        else:
            try:
                volume_filter = float(arg)
            except ValueError:
                raise ValueError(arg)

    return provider_filter, type_filter, volume_filter


def build_filter_description(provider_filter: ProviderName | None, type_filter: str | None) -> str:
    """Build a human-readable description of applied filters."""
    parts = []
    if provider_filter:
        parts.append(f"provider {provider_filter.value}")
    if type_filter:
        parts.append(f"type {type_filter}")
    return " + ".join(parts) if parts else "all data"


def build_prices_output(
    coins: Coins,
    books: OrderBooks,
    type_filter: str | None,
    volume: float | None = None,
) -> str:
    """Build the prices message based on type filter and optional volume for OrderBooks."""
    from decimal import Decimal
    
    lines = []
    
    if type_filter == "OTC" or type_filter is None:
        lines.append(f"OTC prices:\n{coins}")
    
    if type_filter == "P2P":
        lines.append("")
    
    if type_filter == "P2P" or type_filter is None:
        if volume is not None:
            orderbooks_str = books.to_string(Decimal(str(volume)))
        else:
            orderbooks_str = str(books)
        lines.append(f"Order books (P2P):\n{orderbooks_str}")
    
    return "\n".join(lines)


async def send_message_chunked(update: Update, text: str) -> None:
    """Send message, splitting into chunks if needed."""
    if update.message is None:
        return
    if len(text) > 4096:
        for i in range(0, len(text), 4096):
            await update.message.reply_text(text[i:i + 4096])
    else:
        await update.message.reply_text(text)


async def prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with prices, optionally filtered by provider and/or type, with optional volume.
    
    Usage:
        /prices                              - all prices
        /prices aban_tether                  - specific provider
        /prices otc                          - specific type
        /prices aban_tether otc              - provider and type
        /prices otc aban_tether              - order doesn't matter
        /prices 100                          - all prices with VWAP for volume 100
        /prices aban_tether 50               - provider with VWAP for volume 50
        /prices p2p 25.5                     - P2P only with VWAP for volume 25.5
    
    Note: Volume argument is only used for OrderBooks (P2P).
    """
    if update.message is None or context.args is None:
        return
    try:
        provider_filter, type_filter, volume = parse_price_filters(context.args)
    except ValueError as e:
        await update.message.reply_text(
            f"Invalid argument: {e}\n"
            "Valid providers: " + ", ".join([p.value for p in ProviderName]) + "\n"
            "Valid types: OTC, P2P\n"
            "Volume: any positive number (for OrderBooks only)"
        )
        return

    filter_desc = build_filter_description(provider_filter, type_filter)
    if volume is not None:
        filter_desc += f" + volume {volume}"
    timestamp = _cache_updated_at.strftime('%H:%M:%S')
    
    coins_to_show = filter_coins_by_provider(_cached_coins, provider_filter) if provider_filter else _cached_coins
    books_to_show = filter_orderbooks_by_provider(_cached_orderbooks, provider_filter) if provider_filter else _cached_orderbooks
    
    prices_output = build_prices_output(coins_to_show, books_to_show, type_filter, volume)
    msg = f"Market data ({filter_desc}, updated at {timestamp})\n\n{prices_output}"
    
    await send_message_chunked(update, msg)


def filter_coins_by_provider(coins: Coins, provider: ProviderName) -> Coins:
    """Filter coins by provider name."""
    filtered = Coins()
    for coin in coins.coins.values():
        if coin.provider == provider:
            filtered.upsert(coin)
    return filtered


def filter_orderbooks_by_provider(books: OrderBooks, provider: ProviderName) -> OrderBooks:
    """Filter order books by provider name."""
    filtered = OrderBooks()
    for book in books.books.values():
        if book.get_provider() == provider:
            filtered.upsert(book)
    return filtered


# ─── Bot startup ─────────────────────────────────────────────

async def run_bot():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        sys.exit(1)

    # Initialize database with retries
    print("Initializing database...")
    max_retries = 10
    initial_delay = 10  # Wait 10 seconds before first attempt
    
    await asyncio.sleep(initial_delay)
    
    for attempt in range(1, max_retries + 1):
        try:
            await init_db()
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"Error: Failed to initialize database after {max_retries} attempts: {e}")
                sys.exit(1)
            print(f"Attempt {attempt}/{max_retries}: Database not ready, retrying in 5s...")
            await asyncio.sleep(5)

    # Load latest snapshot from database
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

    app.add_handler(CommandHandler("prices", prices_command))

    job_queue = app.job_queue
    if job_queue is None:
        print("Error: JobQueue not available. Install python-telegram-bot[job-queue].")
        sys.exit(1)

    job_queue.run_once(update_cache, when=0)
    job_queue.run_repeating(update_cache, interval=INTERVAL)

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
        await close_db()
