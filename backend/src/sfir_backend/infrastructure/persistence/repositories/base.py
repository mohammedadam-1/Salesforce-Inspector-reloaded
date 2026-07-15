import uuid
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT]:
    """Base repository with common CRUD operations.

    All repositories should inherit from this class and implement
    the mapping between ORM models and domain entities.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, model_class: type[ModelT], id: uuid.UUID) -> ModelT | None:
        result = await self._session.get(model_class, id)
        return result

    async def exists(
        self,
        model_class: type[ModelT],
        criteria: dict[str, Any],
    ) -> bool:
        query = select(model_class)
        for key, value in criteria.items():
            query = query.where(getattr(model_class, key) == value)
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def count(
        self,
        model_class: type[ModelT],
        criteria: dict[str, Any] | None = None,
    ) -> int:
        from sqlalchemy import func

        query = select(func.count()).select_from(model_class)
        if criteria:
            for key, value in criteria.items():
                query = query.where(getattr(model_class, key) == value)
        result = await self._session.execute(query)
        return result.scalar_one() or 0

    async def save(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self._session.delete(instance)
        await self._session.flush()
