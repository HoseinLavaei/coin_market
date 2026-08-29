"""
Database initialisation: creates the unified subscriptions table if it doesn't exist.
"""

import urllib.parse

import asyncpg

import logger
from ..environment import DATABASE_URL


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
            # Create unified subscriptions table if not exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id              SERIAL PRIMARY KEY,
                    user_id         BIGINT  NOT NULL UNIQUE,
                    chat_id         BIGINT,                         -- NULL = pending
                    provider        VARCHAR,
                    type_filter     VARCHAR,
                    volume          DECIMAL,
                    repeat_interval INTEGER NOT NULL,
                    last_sent_at    BIGINT,                         -- minutes since epoch
                    activation_key  TEXT UNIQUE,                    -- NULL when active
                    expires_at      BIGINT,                         -- seconds since epoch, NULL when active
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            logger.info("subscriptions table ready (created if not existed)")

            # Indexes – create if not exist
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions (user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_activation_key ON subscriptions (activation_key)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_last_sent_at ON subscriptions (last_sent_at)")
            logger.info("Indexes ready")

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise