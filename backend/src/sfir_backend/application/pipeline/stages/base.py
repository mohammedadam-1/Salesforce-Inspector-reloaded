from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext

logger = structlog.get_logger(__name__)


class PipelineStage(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def execute(self, context: PipelineContext) -> PipelineContext:
        ...
