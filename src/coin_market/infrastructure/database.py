from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ..environment import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def close_db():
    await engine.dispose()
