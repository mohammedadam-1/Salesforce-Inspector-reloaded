from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sfir_backend.config.settings import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session

