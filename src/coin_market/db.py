import os
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Numeric, String, Enum as SQLEnum, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .coin import Quote
from .provider_name import ProviderName


class Base(DeclarativeBase):
    pass


class CoinPrice(Base):
    __tablename__ = "coin_prices"

    # TimeScaleDB requires the time column to be part of the primary key
    timestamp = Column(DateTime(timezone=True), primary_key=True)
    provider = Column(SQLEnum(ProviderName), primary_key=True)
    base = Column(String, primary_key=True)
    quote = Column(SQLEnum(Quote), primary_key=True)
    price = Column(Numeric(precision=20, scale=8), nullable=False)


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@db/coin_market")
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        # Check if we need to drop the table (if it exists but has an 'id' column or is incompatible)
        # This is a bit aggressive but helps in the initial development phase when schema changes
        # For a more production-ready approach, use Alembic migrations.
        # Here we just try to create. If it fails due to existing table, we tell the user.
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'coin_prices') THEN
                    PERFORM create_hypertable('coin_prices', 'timestamp');
                END IF;
            END $$;
        """))


async def save_coins(coins_collection):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)
            for coin in coins_collection.coins.values():
                db_coin = CoinPrice(
                    timestamp=now,
                    provider=coin.provider,
                    base=coin.base,
                    quote=coin.quote,
                    price=coin.current_price
                )
                session.add(db_coin)
        await session.commit()