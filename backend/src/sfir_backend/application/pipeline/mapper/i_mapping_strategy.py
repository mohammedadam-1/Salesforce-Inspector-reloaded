from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.domain.canonical.base import MetadataComponent


class IMappingStrategy(ABC):
    @abstractmethod
    def can_handle(self, parsed: object) -> bool:
        ...

    @abstractmethod
    def map(self, parsed: object) -> MetadataComponent:
        ...
