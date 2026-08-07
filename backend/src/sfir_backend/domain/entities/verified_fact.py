"""VerifiedFact — the retrieval engine's output unit.

A verified fact is one deduplicated metadata component assembled from the
search index, the canonical metadata store, and the dependency graph. It
carries the identity, display/description enrichment, the sources that
contributed to it, a deterministic confidence score, and the supporting
relationship + metadata context a planner or LLM may rely on without ever
querying the stores directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SupportingRelationship:
    """One graph edge touching a fact, as seen from the fact's identity."""

    identity: str
    api_name: str
    metadata_type: str
    relationship_type: str
    direction: str  # "outgoing" (fact -> neighbor) | "incoming" (neighbor -> fact)


@dataclass
class VerifiedFact:
    identity: str
    metadata_type: str
    api_name: str
    developer_name: str
    display_name: str
    description: str
    namespace: str | None
    source: str  # comma-joined contributing sources, e.g. "search_index,canonical,graph"
    confidence: float
    search_score: float
    relationship_score: int
    reference_count: int
    graph_distance: int
    object_api_name: str = ""
    supporting_relationships: list[SupportingRelationship] = field(
        default_factory=list,
    )
    supporting_metadata: dict = field(default_factory=dict)
