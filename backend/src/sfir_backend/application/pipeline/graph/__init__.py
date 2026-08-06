"""Dependency graph construction from canonical data.

Phase 6: the graph builder derives the persisted dependency graph purely
from the canonical store (current-state documents and active relationships)
— it never reads Salesforce metadata, normalized documents, or the legacy
in-memory graph.
"""

from sfir_backend.application.pipeline.graph.dependency_graph_builder import (
    DependencyGraphBuilder,
    DependencyGraphBuildResult,
)

__all__ = ["DependencyGraphBuildResult", "DependencyGraphBuilder"]
