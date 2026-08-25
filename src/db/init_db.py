"""
Database initialisation: creates only subscriptions and pending_subscriptions tables if they don't exist.
"""

import urllib.parse

import asyncpg

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
            # ─── Subscriptions table ────────────────────────────────
            # Drop and recreate to ensure clean schema
            await conn.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
            await conn.execute("""
                               CREATE TABLE subscriptions
                               (
                                   id              SERIAL PRIMARY KEY,
                                   user_id         BIGINT  NOT NULL UNIQUE,
                                   chat_id         BIGINT  NOT NULL UNIQUE,
                                   provider        VARCHAR,
                                   type_filter     VARCHAR,
                                   volume          DECIMAL,
                                   repeat_interval INTEGER NOT NULL,
                                   last_sent_at    BIGINT,
                                   created_at      TIMESTAMPTZ DEFAULT NOW(),
                                   updated_at      TIMESTAMPTZ DEFAULT NOW()
                               )
                               """)
            print("subscriptions table ready")

            # ─── Pending subscriptions table ─────────────────────────
            await conn.execute("DROP TABLE IF EXISTS pending_subscriptions CASCADE")
            await conn.execute("""
                               CREATE TABLE pending_subscriptions
                               (
                                   key             TEXT PRIMARY KEY,
                                   user_id         BIGINT  NOT NULL,
                                   provider        VARCHAR,
                                   type_filter     VARCHAR,
                                   volume          DECIMAL,
                                   repeat_interval INTEGER NOT NULL,
                                   chat_id         BIGINT,
                                   status          VARCHAR     DEFAULT 'pending',
                                   expires_at      BIGINT  NOT NULL,
                                   created_at      TIMESTAMPTZ DEFAULT NOW()
                               )
                               """)
            print("pending_subscriptions table ready")

            # ─── Indexes ──────────────────────────────────────────────
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions (user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_chat_id ON subscriptions (chat_id)")
            print("indexes ready")

        finally:
            await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise
