"""Retrieval engine — the only gateway to the canonical stores.

The retrieval engine is the sole component allowed to query the search
index, the canonical metadata store, and the dependency graph. It turns a
query into ranked, deduplicated verified facts with timeout budgets and
partial-failure tolerance, for downstream consumers (planner / LLM) that
never query those stores directly.
"""

from sfir_backend.application.retrieval.retrieval_engine import (
    RetrievalEngine,
    RetrievalRequest,
    RetrievalResult,
    SourceFailure,
)

__all__ = [
    "RetrievalEngine",
    "RetrievalRequest",
    "RetrievalResult",
    "SourceFailure",
]
