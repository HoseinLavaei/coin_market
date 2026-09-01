"""
Database engine and session factory for async SQLAlchemy.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.environment import DATABASE_URL

# Async engine with connection pooling (disabled SQL echo for production)
engine = create_async_engine(DATABASE_URL, echo=False)

# Session maker for async operations
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def close_db() -> None:
    """Dispose of the database engine and release all connections."""
    await engine.dispose()
