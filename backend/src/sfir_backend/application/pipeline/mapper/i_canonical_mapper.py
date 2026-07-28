from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.domain.canonical.base import MetadataComponent


class ICanonicalMapper(ABC):
    @abstractmethod
    def map(self, parsed: list) -> list[MetadataComponent]:
        ...
