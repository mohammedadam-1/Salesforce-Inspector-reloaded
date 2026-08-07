"""Search index construction from canonical data.

Phase 7: the search index builder derives searchable documents purely from
the canonical store (current-state documents), the dependency graph
(nodes and edges), and canonical relationships — it never reads Salesforce
metadata, normalized documents, or the legacy in-memory search engine.
"""

from sfir_backend.application.pipeline.search.search_index_builder import (
    SearchIndexBuilder,
    SearchIndexBuildResult,
)

__all__ = ["SearchIndexBuildResult", "SearchIndexBuilder"]
