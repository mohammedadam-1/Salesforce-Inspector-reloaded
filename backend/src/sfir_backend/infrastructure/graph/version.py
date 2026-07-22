from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sfir_backend.domain.graph.models import (
    Graph,
    GraphSnapshot,
    GraphVersion,
)


class GraphVersionManager:
    def __init__(self) -> None:
        self._versions: dict[str, GraphVersion] = {}
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._current_version: str = ""

    @property
    def current_version(self) -> str:
        return self._current_version

    def create_version(
        self,
        graph: Graph,
        parent_version: str | None = None,
        change_summary: str = "",
    ) -> GraphVersion:
        version_id = str(uuid4())
        version = GraphVersion(
            version=version_id,
            parent_version=parent_version or self._current_version or None,
            created_at=datetime.now(tz=UTC),
            node_count=graph.node_count,
            edge_count=graph.edge_count,
            change_summary=change_summary,
        )
        self._versions[version_id] = version
        self._current_version = version_id
        return version

    def create_snapshot(
        self,
        graph: Graph,
        change_summary: str = "",
    ) -> GraphSnapshot:
        version = self.create_version(graph, change_summary=change_summary)
        snapshot = GraphSnapshot(
            version=version.version,
            snapshot_id=str(uuid4()),
            created_at=datetime.now(tz=UTC),
            graph=graph.model_copy(deep=True),
            version_info=version,
        )
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot | None:
        return self._snapshots.get(snapshot_id)

    def get_version(self, version: str) -> GraphVersion | None:
        return self._versions.get(version)

    def list_versions(self) -> list[GraphVersion]:
        return list(self._versions.values())

    def list_snapshots(self) -> list[GraphSnapshot]:
        return list(self._snapshots.values())

    def rollback_to_version(self, version: str) -> GraphSnapshot | None:
        for snapshot in self._snapshots.values():
            if snapshot.version == version:
                return snapshot
        return None
