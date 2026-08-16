"""
Database initialisation: creates TimescaleDB extension and all tables if they don't exist.
Uses raw asyncpg for DDL operations (SQLAlchemy's create_all is not used for TimescaleDB).
"""

import urllib.parse

import asyncpg

from ..environment import DATABASE_URL


async def init_db():
    """
    Connect to the database and create all required tables and indexes.
    TimescaleDB extension is enabled to support time‑series hypertables.
    """
    try:
        parsed = urllib.parse.urlparse(DATABASE_URL)
        host = parsed.hostname
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        database = parsed.path.lstrip("/")

        conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)

        try:
            # Enable TimescaleDB extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
            print("TimescaleDB extension is ready.")

            # Core market data tables
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS coin
                               (
                                   coin_id        SERIAL PRIMARY KEY,
                                   provider       VARCHAR     NOT NULL,
                                   base           VARCHAR     NOT NULL,
                                   quote          VARCHAR     NOT NULL,
                                   raw_buy_price  DECIMAL     NOT NULL,
                                   raw_sell_price DECIMAL     NOT NULL,
                                   buy_fee        DECIMAL     NOT NULL,
                                   sell_fee       DECIMAL     NOT NULL,
                                   timestamp      TIMESTAMPTZ NOT NULL
                               )
                               """)
            print("coin table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS "order"
                               (
                                   order_id SERIAL PRIMARY KEY,
                                   coin_id  INTEGER REFERENCES coin (coin_id) NOT NULL,
                                   quantity DECIMAL                           NOT NULL
                               )
                               """)
            print("order table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS orderbook
                               (
                                   orderbook_id SERIAL PRIMARY KEY,
                                   asks_ids     INTEGER[],
                                   bids_ids     INTEGER[]
                               )
                               """)
            print("orderbook table ready")

            # Collection tables for grouping IDs by (provider, base, quote)
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS coins
                               (
                                   coins_id SERIAL PRIMARY KEY,
                                   provider VARCHAR NOT NULL,
                                   base     VARCHAR NOT NULL,
                                   quote    VARCHAR NOT NULL,
                                   coin_ids INTEGER[]
                               )
                               """)
            print("coins table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS orderbooks
                               (
                                   orderbooks_id SERIAL PRIMARY KEY,
                                   provider      VARCHAR NOT NULL,
                                   base          VARCHAR NOT NULL,
                                   quote         VARCHAR NOT NULL,
                                   orderbook_ids INTEGER[]
                               )
                               """)
            print("orderbooks table ready")

            # Subscription tables
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS pending_subscriptions
                               (
                                   key             TEXT PRIMARY KEY,
                                   user_id         BIGINT      NOT NULL,
                                   provider        VARCHAR,
                                   type_filter     VARCHAR,
                                   volume          DECIMAL,
                                   repeat_interval INT,
                                   chat_id         BIGINT,
                                   status          VARCHAR     DEFAULT 'pending',
                                   created_at      TIMESTAMPTZ DEFAULT NOW(),
                                   expires_at      TIMESTAMPTZ NOT NULL,
                                   CONSTRAINT check_pending_status_valid CHECK (status IN ('pending', 'claimed', 'expired'))
                               )
                               """)
            print("pending_subscriptions table ready")

            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS subscriptions
                               (
                                   id              SERIAL PRIMARY KEY,
                                   chat_id         BIGINT NOT NULL,
                                   user_id         BIGINT NOT NULL,
                                   provider        VARCHAR,
                                   type_filter     VARCHAR,
                                   volume          DECIMAL,
                                   repeat_interval INT,
                                   status          VARCHAR     DEFAULT 'active',
                                   created_at      TIMESTAMPTZ DEFAULT NOW(),
                                   updated_at      TIMESTAMPTZ DEFAULT NOW(),
                                   CONSTRAINT check_repeat_interval_positive CHECK (repeat_interval IS NULL OR repeat_interval > 0),
                                   CONSTRAINT check_status_valid CHECK (status IN ('active', 'paused'))
                               )
                               """)
            print("subscriptions table ready")

            # Indexes for common query patterns
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions (user_id)")
            print("subscriptions indexes ready")

        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise
