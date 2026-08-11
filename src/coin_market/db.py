import urllib.parse
from datetime import datetime
from decimal import Decimal
from typing import cast

import asyncpg
import sqlalchemy as sa
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import CheckConstraint

from .base import Base
from .coin import Base as CoinBase, Quote
from .coin import Coin as PydanticCoin
from .coin import Coins as PydanticCoins
from .coin import Order as PydanticOrder
from .coin import OrderBook as PydanticOrderBook
from .coin import OrderBooks as PydanticOrderBooks
from .environment import DATABASE_URL, TIMEZONE
from .provider_name import ProviderName
from .subscription import Subscription


# ─── SQLAlchemy relational models ──────────────────────────

class Coin(Base):
    __tablename__ = "coin"

    coin_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    _buy_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    _sell_price: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    buy_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    sell_fee: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)


class Order(Base):
    __tablename__ = "order"

    order_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    coin_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("coin.coin_id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(sa.DECIMAL, nullable=False)


class OrderBook(Base):
    __tablename__ = "orderbook"

    orderbook_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    asks_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)
    bids_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class Coins(Base):
    __tablename__ = "coins"

    coins_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    coin_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class OrderBooks(Base):
    __tablename__ = "orderbooks"

    orderbooks_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(sa.String, nullable=False)
    base: Mapped[str] = mapped_column(sa.String, nullable=False)
    quote: Mapped[str] = mapped_column(sa.String, nullable=False)
    orderbook_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.Integer), nullable=True)


class PendingSubscription(Base):
    __tablename__ = "pending_subscriptions"

    key: Mapped[str] = mapped_column(sa.String, primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    provider: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    type_filter: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(sa.DECIMAL, nullable=True)
    repeat_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(sa.String, default="pending")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'claimed', 'expired')", name="check_pending_status_valid"),
    )


# ─── Engine and session ─────────────────────────────────────

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─── init_db ──────────────────────────────────────────────────

async def init_db():
    try:
        parsed = urllib.parse.urlparse(DATABASE_URL)
        host = parsed.hostname
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        database = parsed.path.lstrip("/")

        conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)

        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
            print("TimescaleDB extension is ready.")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS coin (
                    coin_id SERIAL PRIMARY KEY,
                    provider VARCHAR NOT NULL,
                    base VARCHAR NOT NULL,
                    quote VARCHAR NOT NULL,
                    _buy_price DECIMAL NOT NULL,
                    _sell_price DECIMAL NOT NULL,
                    buy_fee DECIMAL NOT NULL,
                    sell_fee DECIMAL NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL
                )
            """)
            print("coin table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS "order" (
                    order_id SERIAL PRIMARY KEY,
                    coin_id INTEGER REFERENCES coin(coin_id) NOT NULL,
                    quantity DECIMAL NOT NULL
                )
            """)
            print("order table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orderbook (
                    orderbook_id SERIAL PRIMARY KEY,
                    asks_ids INTEGER[],
                    bids_ids INTEGER[]
                )
            """)
            print("orderbook table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS coins (
                    coins_id SERIAL PRIMARY KEY,
                    provider VARCHAR NOT NULL,
                    base VARCHAR NOT NULL,
                    quote VARCHAR NOT NULL,
                    coin_ids INTEGER[]
                )
            """)
            print("coins table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orderbooks (
                    orderbooks_id SERIAL PRIMARY KEY,
                    provider VARCHAR NOT NULL,
                    base VARCHAR NOT NULL,
                    quote VARCHAR NOT NULL,
                    orderbook_ids INTEGER[]
                )
            """)
            print("orderbooks table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_subscriptions (
                    key TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    provider VARCHAR,
                    type_filter VARCHAR,
                    volume DECIMAL,
                    repeat_interval INT,
                    chat_id BIGINT,
                    status VARCHAR DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    CONSTRAINT check_pending_status_valid CHECK (status IN ('pending', 'claimed', 'expired'))
                )
            """)
            print("pending_subscriptions table ready")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    provider VARCHAR,
                    type_filter VARCHAR,
                    volume DECIMAL,
                    repeat_interval INT,
                    status VARCHAR DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT check_repeat_interval_positive CHECK (repeat_interval IS NULL OR repeat_interval > 0),
                    CONSTRAINT check_status_valid CHECK (status IN ('active', 'paused'))
                )
            """)
            print("subscriptions table ready")

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)
            """)
            print("subscriptions index ready")

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions (user_id)
            """)
            print("subscriptions user_id index ready")

        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


# ─── Helper to generate unique coin key ────────────────────

def _coin_key(coin: PydanticCoin) -> tuple[str, str, str, str, str]:
    # noinspection PyProtectedMember
    return (
        coin.provider.name,
        coin.base.name,
        coin.quote.name,
        str(coin._buy_price),
        str(coin._sell_price),
    )


# ─── Helpers to convert SQLAlchemy models to Pydantic ─────

def _to_pydantic_coin(cm: Coin) -> PydanticCoin:
    # noinspection PyProtectedMember
    return PydanticCoin(
        provider=ProviderName[cm.provider],
        base=CoinBase[cm.base],
        quote=Quote[cm.quote],
        _buy_price=cm._buy_price,
        _sell_price=cm._sell_price,
        buy_fee=cm.buy_fee,
        sell_fee=cm.sell_fee,
        timestamp=cm.timestamp,
    )


def _build_order_map(order_coin_pairs: list[tuple[Order, Coin]]) -> dict[int, PydanticOrder]:
    order_map: dict[int, PydanticOrder] = {}
    for order, coin in order_coin_pairs:
        order_map[order.order_id] = PydanticOrder(
            coin=_to_pydantic_coin(coin),
            quantity=order.quantity,
        )
    return order_map


async def _load_orderbooks(
        session: AsyncSession,
        order_ids: list[int],
        order_map: dict[int, PydanticOrder],
) -> PydanticOrderBooks:
    ob_rows = await session.execute(
        sa.select(OrderBook).where(
            sa.or_(
                OrderBook.asks_ids.op('&&')(order_ids),
                OrderBook.bids_ids.op('&&')(order_ids)
            )
        )
    )
    orderbooks = PydanticOrderBooks()
    for obm in ob_rows.scalars().all():
        asks = [order_map[oid] for oid in (obm.asks_ids or []) if oid in order_map]
        bids = [order_map[oid] for oid in (obm.bids_ids or []) if oid in order_map]
        if asks or bids:
            first = asks[0] if asks else bids[0]
            key = (first.coin.provider, first.coin.quote, first.coin.base)
            orderbooks.books[key] = PydanticOrderBook(asks=asks, bids=bids)
    return orderbooks


# ─── Save snapshot helpers ─────────────────────────────────

async def _insert_otc_coins(
        session: AsyncSession,
        coins: PydanticCoins,
        now: datetime,
) -> dict[tuple[str, str, str, str, str], int]:
    coin_id_map: dict[tuple[str, str, str, str, str], int] = {}
    for key, coin in coins.coins.items():
        # noinspection PyProtectedMember
        coin_model = Coin(
            provider=coin.provider.name,
            base=coin.base.name,
            quote=coin.quote.name,
            _buy_price=coin._buy_price,
            _sell_price=coin._sell_price,
            buy_fee=coin.buy_fee,
            sell_fee=coin.sell_fee,
            timestamp=now,
        )
        session.add(coin_model)
        await session.flush()
        coin_key = _coin_key(coin)
        coin_id_map[coin_key] = coin_model.coin_id
    return coin_id_map


async def _insert_orderbook_coins(
        session: AsyncSession,
        orderbooks: PydanticOrderBooks,
        coin_id_map: dict[tuple[str, str, str, str, str], int],
        now: datetime,
) -> None:
    for book in orderbooks.books.values():
        for order in book.asks + book.bids:
            coin = order.coin
            coin_key = _coin_key(coin)
            if coin_key not in coin_id_map:
                # noinspection PyProtectedMember
                coin_model = Coin(
                    provider=coin.provider.name,
                    base=coin.base.name,
                    quote=coin.quote.name,
                    _buy_price=coin._buy_price,
                    _sell_price=coin._sell_price,
                    buy_fee=coin.buy_fee,
                    sell_fee=coin.sell_fee,
                    timestamp=now,
                )
                session.add(coin_model)
                await session.flush()
                coin_id_map[coin_key] = coin_model.coin_id


async def _insert_orders_and_orderbooks(
        session: AsyncSession,
        orderbooks: PydanticOrderBooks,
        coin_id_map: dict[tuple[str, str, str, str, str], int],
) -> dict[tuple[ProviderName, Quote, CoinBase], int]:
    orderbook_id_map: dict[tuple[ProviderName, Quote, CoinBase], int] = {}
    for key, book in orderbooks.books.items():
        provider, quote, base = key
        asks_ids: list[int] = []
        bids_ids: list[int] = []

        for order in book.asks:
            coin_key = _coin_key(order.coin)
            coin_id = coin_id_map[coin_key]
            order_model = Order(
                coin_id=coin_id,
                quantity=order.quantity,
            )
            session.add(order_model)
            await session.flush()
            asks_ids.append(order_model.order_id)

        for order in book.bids:
            coin_key = _coin_key(order.coin)
            coin_id = coin_id_map[coin_key]
            order_model = Order(
                coin_id=coin_id,
                quantity=order.quantity,
            )
            session.add(order_model)
            await session.flush()
            bids_ids.append(order_model.order_id)

        ob_model = OrderBook(
            asks_ids=asks_ids,
            bids_ids=bids_ids,
        )
        session.add(ob_model)
        await session.flush()
        orderbook_id_map[(provider, quote, base)] = ob_model.orderbook_id

    return orderbook_id_map


async def _insert_collections(
        session: AsyncSession,
        coin_id_map: dict[tuple[str, str, str, str, str], int],
        orderbook_id_map: dict[tuple[ProviderName, Quote, CoinBase], int],
) -> None:
    # Coin collections
    group_coin_ids: dict[tuple[str, str, str], list[int]] = {}
    for coin_key, coin_id in coin_id_map.items():
        provider, base, quote, _, _ = coin_key
        group_key = (provider, base, quote)
        group_coin_ids.setdefault(group_key, []).append(coin_id)

    for (provider_name, base_name, quote_name), coin_ids in group_coin_ids.items():
        collection = Coins(
            provider=provider_name,
            base=base_name,
            quote=quote_name,
            coin_ids=coin_ids,
        )
        session.add(collection)

    # OrderBook collections
    orderbook_collection_map: dict[tuple[str, str, str], list[int]] = {}
    for (provider, quote, base), ob_id in orderbook_id_map.items():
        key = (provider.name, quote.name, base.name)
        orderbook_collection_map.setdefault(key, []).append(ob_id)

    for (provider_name, quote_name, base_name), ob_ids in orderbook_collection_map.items():
        collection = OrderBooks(
            provider=provider_name,
            base=base_name,
            quote=quote_name,
            orderbook_ids=ob_ids,
        )
        session.add(collection)


async def save_snapshot(coins: PydanticCoins, orderbooks: PydanticOrderBooks) -> None:
    async with AsyncSessionLocal() as session:
        now = datetime.now()
        coin_id_map = await _insert_otc_coins(session, coins, now)
        await _insert_orderbook_coins(session, orderbooks, coin_id_map, now)
        orderbook_id_map = await _insert_orders_and_orderbooks(session, orderbooks, coin_id_map)
        await _insert_collections(session, coin_id_map, orderbook_id_map)
        await session.commit()


# ─── Load latest snapshot ──────────────────────────────────

async def load_latest_snapshot() -> tuple[PydanticCoins, PydanticOrderBooks] | None:
    async with AsyncSessionLocal() as session:
        latest_ts_result = await session.execute(
            sa.select(func.max(Coin.timestamp))
        )
        latest_ts = latest_ts_result.scalar_one_or_none()
        if latest_ts is None:
            return None

        coin_rows = await session.execute(
            sa.select(Coin).where(Coin.timestamp == latest_ts)
        )
        coins = PydanticCoins()
        for cm in coin_rows.scalars().all():
            coins.upsert(_to_pydantic_coin(cm))

        order_coin_rows = await session.execute(
            sa.select(Order, Coin)
            .join(Coin, Order.coin_id == Coin.coin_id)
            .where(Coin.timestamp == latest_ts)
        )
        order_coin_pairs: list[tuple[Order, Coin]] = [(row[0], row[1]) for row in order_coin_rows]
        order_map = _build_order_map(order_coin_pairs)

        if not order_map:
            return coins, PydanticOrderBooks()

        order_ids = list(order_map.keys())
        orderbooks = await _load_orderbooks(session, order_ids, order_map)

        return coins, orderbooks


# ─── Subscription helpers ──────────────────────────────────

async def add_subscription(
        chat_id: int,
        user_id: int,
        provider: str | None = None,
        type_filter: str | None = None,
        volume: Decimal | None = None,
        repeat_interval: int | None = None,
) -> Subscription:
    async with AsyncSessionLocal() as session:
        sub = Subscription(
            chat_id=chat_id,
            user_id=user_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            status="active",
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


async def get_subscriptions_for_user(user_id: int) -> list[Subscription]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return list(result.scalars().all())


async def get_active_subscriptions() -> list[Subscription]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status == "active",
                    Subscription.repeat_interval.is_not(None)
                )
            )
        )
        return list(result.scalars().all())


async def pause_subscription_by_id(sub_id: int, user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(and_(Subscription.id == sub_id, Subscription.user_id == user_id))
            .values(status="paused", updated_at=datetime.now())
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


async def resume_subscription_by_id(sub_id: int, user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(and_(Subscription.id == sub_id, Subscription.user_id == user_id, Subscription.status == "paused"))
            .values(status="active", updated_at=datetime.now())
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


async def delete_subscription_by_id(sub_id: int, user_id: int) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subscription)
            .where(and_(Subscription.id == sub_id, Subscription.user_id == user_id))
        )
        await session.commit()
        # noinspection PyUnresolvedReferences
        return result.rowcount


# ─── Pending subscription helpers ──────────────────────────

async def create_pending_subscription(
    key: str,
    user_id: int,
    provider: str | None,
    type_filter: str | None,
    volume: Decimal | None,
    repeat_interval: int | None,
    expires_at: datetime,
) -> PendingSubscription:
    async with AsyncSessionLocal() as session:
        pending = PendingSubscription(
            key=key,
            user_id=user_id,
            provider=provider,
            type_filter=type_filter,
            volume=volume,
            repeat_interval=repeat_interval,
            expires_at=expires_at,
            status="pending",
        )
        session.add(pending)
        await session.commit()
        await session.refresh(pending)
        return pending


async def claim_pending_subscription(key: str, chat_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingSubscription)
            .where(PendingSubscription.key == key)
            .with_for_update()
        )
        pending = result.scalar_one_or_none()
        if pending is None:
            return None

        pending = cast(PendingSubscription, pending)

        if pending.status != "pending":
            return None
        if pending.expires_at < datetime.now(TIMEZONE):
            pending.status = "expired"
            await session.commit()
            return None

        pending.chat_id = chat_id
        pending.status = "claimed"
        await session.commit()

        return {
            "user_id": pending.user_id,
            "provider": pending.provider,
            "type_filter": pending.type_filter,
            "volume": pending.volume,
            "repeat_interval": pending.repeat_interval,
            "chat_id": chat_id,
        }


async def delete_pending_subscription(key: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PendingSubscription).where(PendingSubscription.key == key)
        )
        await session.commit()


async def close_db():
    await engine.dispose()