from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sfir_backend.config.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the SQLAlchemy async engine with connection pooling."""
    return create_async_engine(
        url=settings.database_url.get_secret_value(),
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


SessionFactory = async_sessionmaker[AsyncSession]


@asynccontextmanager
async def session_scope(
    session_factory: SessionFactory,
) -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations.

    Usage:
        async with session_scope(session_factory) as session:
            session.add(some_object)
    """
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
