"""Abstract base repository with common CRUD operations."""

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
    ) -> tuple[Sequence[ModelT], int]:
        query = select(self._model)
        if filters:
            for field, value in filters.items():
                if hasattr(self._model, field):
                    query = query.where(getattr(self._model, field) == value)
        if order_by and hasattr(self._model, order_by):
            query = query.order_by(getattr(self._model, order_by))
        count_query = select(self._model.id).select_from(self._model)
        if filters:
            for field, value in filters.items():
                if hasattr(self._model, field):
                    count_query = count_query.where(
                        getattr(self._model, field) == value
                    )
        total_result = await self._session.execute(count_query)
        total = len(total_result.all())
        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all(), total

    async def create(self, model: ModelT) -> ModelT:
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(self, model: ModelT) -> ModelT:
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, model: ModelT) -> None:
        await self._session.delete(model)
        await self._session.flush()

    async def exists(self, id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(self._model.id).where(self._model.id == id)
        )
        return result.scalar_one_or_none() is not None
