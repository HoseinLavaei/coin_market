import json
import os
import urllib.parse
from datetime import datetime
from decimal import Decimal

import asyncpg
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

from . import Coins, Coin, OrderBooks, OrderBook, Base as CoinBase, Quote
from .coin import Order
from .provider_name import ProviderName

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Use async_sessionmaker for async sessions
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


class MarketSnapshot(Base):
    """Store complete market snapshots with coins and orderbooks."""
    __tablename__ = "market_snapshots"

    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), primary_key=True, index=True)
    coins: Mapped[str] = mapped_column(JSONB, nullable=False)
    orderbooks: Mapped[str] = mapped_column(JSONB, nullable=False)


async def init_db():
    """Initialize the database and create tables."""
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")

        parsed = urllib.parse.urlparse(db_url)
        host = parsed.hostname
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        database = parsed.path.lstrip("/")

        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )

        try:
            # Enable TimescaleDB extension
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
                print("TimescaleDB extension created/verified")
            except Exception as e:
                print(f"Warning: Could not create TimescaleDB extension: {e}")

            # Create market_snapshots table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    timestamp TIMESTAMPTZ PRIMARY KEY,
                    coins JSONB NOT NULL,
                    orderbooks JSONB NOT NULL
                )
            """)
            print("Created market_snapshots table")

            # Convert to hypertable if not already
            try:
                await conn.execute("""
                    SELECT create_hypertable('market_snapshots', 'timestamp', if_not_exists => TRUE)
                """)
                print("Created TimescaleDB hypertable for market_snapshots")
            except asyncpg.UniqueViolationError:
                print("market_snapshots is already a hypertable")
            except Exception as e:
                print(f"Note: {e}")
        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


def _coin_to_dict(coin: Coin) -> dict:
    """Convert Coin to JSON-serializable dict."""
    return {
        "provider": coin.provider.name,
        "base": coin.base.name,
        "buy_price": str(coin.buy_price),
        "sell_price": str(coin.sell_price),
        "quote": coin.quote.name,
        "timestamp": coin.timestamp.isoformat(),
    }


def _dict_to_coin(data: dict) -> Coin:
    """Convert dict back to Coin."""
    return Coin(
        provider=ProviderName[data["provider"]],
        base=CoinBase[data["base"]],
        buy_price=Decimal(data["buy_price"]),
        sell_price=Decimal(data["sell_price"]),
        quote=Quote[data["quote"]],
        timestamp=datetime.fromisoformat(data["timestamp"]),
    )


def _order_to_dict(order: Order) -> dict:
    """Convert Order to JSON-serializable dict."""
    return {
        "coin": _coin_to_dict(order.coin),
        "quantity": str(order.quantity),
    }


def _dict_to_order(data: dict) -> Order:
    """Convert dict back to Order."""
    return Order(
        coin=_dict_to_coin(data["coin"]),
        quantity=Decimal(data["quantity"]),
    )


def _orderbook_to_dict(book: OrderBook) -> dict:
    """Convert OrderBook to JSON-serializable dict."""
    return {
        "asks": [_order_to_dict(order) for order in book.asks],
        "bids": [_order_to_dict(order) for order in book.bids],
    }


def _dict_to_orderbook(data: dict) -> OrderBook:
    """Convert dict back to OrderBook."""
    return OrderBook(
        asks=[_dict_to_order(order_data) for order_data in data["asks"]],
        bids=[_dict_to_order(order_data) for order_data in data["bids"]],
    )


def _coins_to_json(coins: Coins) -> str:
    """Convert Coins collection to JSON array (from dict values)."""
    coin_dicts = [_coin_to_dict(coin) for coin in coins.coins.values()]
    return json.dumps(coin_dicts)


def _json_to_coins(json_str: str) -> Coins:
    """Convert JSON array back to Coins collection."""
    coin_dicts = json.loads(json_str)
    coins = Coins()
    for coin_dict in coin_dicts:
        coin = _dict_to_coin(coin_dict)
        coins.upsert(coin)
    return coins


def _orderbooks_to_json(books: OrderBooks) -> str:
    """Convert OrderBooks collection to JSON array (from dict values)."""
    book_dicts = [_orderbook_to_dict(book) for book in books.books.values()]
    return json.dumps(book_dicts)


def _json_to_orderbooks(json_str: str) -> OrderBooks:
    """Convert JSON array back to OrderBooks collection."""
    book_dicts = json.loads(json_str)
    books = OrderBooks()
    for book_dict in book_dicts:
        book = _dict_to_orderbook(book_dict)
        books.upsert(book)
    return books


async def load_latest_snapshot() -> tuple[Coins, OrderBooks] | None:
    """Load the most recent market snapshot from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.select(MarketSnapshot)
            .order_by(MarketSnapshot.timestamp.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            return None

        # Use getattr with fallback to satisfy type checker
        coins_data = getattr(snapshot, 'coins', '{}')
        orderbooks_data = getattr(snapshot, 'orderbooks', '{}')

        # Ensure we have valid JSON strings
        if not coins_data or not orderbooks_data:
            return None

        coins = _json_to_coins(coins_data)
        orderbooks = _json_to_orderbooks(orderbooks_data)
        return coins, orderbooks


async def save_snapshot(coins: Coins, orderbooks: OrderBooks) -> None:
    """Save a market snapshot to the database."""
    async with AsyncSessionLocal() as session:
        snapshot = MarketSnapshot(
            timestamp=datetime.now(),
            coins=_coins_to_json(coins),
            orderbooks=_orderbooks_to_json(orderbooks),
        )
        session.add(snapshot)
        await session.commit()


async def close_db():
    """Close database connection."""
    await engine.dispose()