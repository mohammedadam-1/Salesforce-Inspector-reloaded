"""ManifestGenerator, MetadataHashCalculator, MetadataChangeDetector, ConflictDetector."""

import hashlib
import json

import structlog

from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.value_objects.metadata import (
    ConflictResolution,
    MetadataAction,
)

logger = structlog.get_logger(__name__)


class MetadataHashCalculator:
    """Computes deterministic hashes for metadata components."""

    @staticmethod
    def compute_hash(data: dict | str) -> str:
        if isinstance(data, str):
            return hashlib.sha256(data.encode("utf-8")).hexdigest()
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_manifest_hash(components: list[dict]) -> str:
        hasher = hashlib.sha256()
        for comp in sorted(components, key=lambda x: json.dumps(x, sort_keys=True)):
            normalized = json.dumps(comp, sort_keys=True, default=str)
            hasher.update(normalized.encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class ManifestGenerator:
    """Generates and compares metadata manifests."""

    @staticmethod
    def generate_manifest(
        components: list[dict],
        component_type: str | None = None,
    ) -> dict:
        manifest: dict[str, list[dict]] = {}
        for comp in components:
            attr = comp.get("attributes", {})
            ctype = component_type or comp.get("type", attr.get("type", "Unknown"))
            if ctype not in manifest:
                manifest[ctype] = []
            manifest[ctype].append({
                "name": comp.get("Name", comp.get("name", "")),
                "id": comp.get("Id", comp.get("id", "")),
                "last_modified": str(comp.get("LastModifiedDate", "")),
                "hash": MetadataHashCalculator.compute_hash(comp),
            })
        return manifest

    @staticmethod
    def manifest_size(manifest: dict) -> int:
        return sum(len(items) for items in manifest.values())

    @staticmethod
    def get_component_names(manifest: dict) -> set[tuple[str, str]]:
        names: set[tuple[str, str]] = set()
        for ctype, items in manifest.items():
            for item in items:
                names.add((ctype, item["name"]))
        return names


class MetadataChangeDetector:
    """Detects changes between two metadata states using hash comparison."""

    def __init__(self) -> None:
        self._hash_calculator = MetadataHashCalculator()

    def detect_changes(
        self,
        old_versions: list[MetadataVersion],
        current_manifest: dict,
    ) -> list[dict]:
        changes: list[dict] = []
        old_map: dict[tuple[str, str], MetadataVersion] = {}
        for v in old_versions:
            old_map[(v.component_type, v.component_name)] = v

        current_set: set[tuple[str, str]] = set()
        for ctype, items in current_manifest.items():
            for item in items:
                key = (ctype, item["name"])
                current_set.add(key)
                old = old_map.get(key)
                if not old:
                    changes.append({
                        "component_type": ctype,
                        "component_name": item["name"],
                        "component_id": item["id"],
                        "action": MetadataAction.CREATED,
                        "hash": item["hash"],
                        "previous_hash": None,
                    })
                elif old.hash != item["hash"]:
                    changes.append({
                        "component_type": ctype,
                        "component_name": item["name"],
                        "component_id": item["id"],
                        "action": MetadataAction.UPDATED,
                        "hash": item["hash"],
                        "previous_hash": old.hash,
                    })

        for key, old_version in old_map.items():
            if key not in current_set:
                changes.append({
                    "component_type": key[0],
                    "component_name": key[1],
                    "component_id": old_version.component_id,
                    "action": MetadataAction.DELETED,
                    "hash": old_version.hash,
                    "previous_hash": None,
                })

        return changes

    def detect_renamed_components(
        self,
        old_versions: list[MetadataVersion],
        current_manifest: dict,
    ) -> list[dict]:
        renamed: list[dict] = []
        old_by_hash: dict[str, list[MetadataVersion]] = {}
        for v in old_versions:
            if v.hash not in old_by_hash:
                old_by_hash[v.hash] = []
            old_by_hash[v.hash].append(v)

        current_set: set[tuple[str, str]] = set()
        for ctype, items in current_manifest.items():
            for item in items:
                current_set.add((ctype, item["name"]))

        for ctype, items in current_manifest.items():
            for item in items:
                key = (ctype, item["name"])
                if key not in {(v.component_type, v.component_name) for v in old_versions}:
                    old_matches = old_by_hash.get(item["hash"], [])
                    for old in old_matches:
                        if old.component_type == ctype:
                            old_key = (old.component_type, old.component_name)
                            if old_key not in current_set and old_key != key:
                                renamed.append({
                                    "component_type": ctype,
                                    "old_name": old.component_name,
                                    "new_name": item["name"],
                                    "component_id": item["id"],
                                    "hash": item["hash"],
                                    "action": "renamed",
                                })
                                break

        return renamed


class ConflictDetector:
    """Detects and resolves conflicts during metadata synchronization."""

    @staticmethod
    def detect_conflicts(
        local_versions: list[MetadataVersion],
        remote_manifest: dict,
    ) -> list[dict]:
        conflicts: list[dict] = []
        local_map: dict[tuple[str, str], MetadataVersion] = {}
        for v in local_versions:
            local_map[(v.component_type, v.component_name)] = v

        for ctype, items in remote_manifest.items():
            for item in items:
                key = (ctype, item["name"])
                local = local_map.get(key)
                if not local:
                    continue
                if local.hash != item["hash"]:
                    conflicts.append({
                        "component_type": ctype,
                        "component_name": item["name"],
                        "local_hash": local.hash,
                        "remote_hash": item["hash"],
                        "local_modified": str(local.sync_timestamp),
                        "remote_modified": item.get("last_modified", ""),
                    })
        return conflicts

    @staticmethod
    def resolve_conflict(
        local_version: MetadataVersion,
        remote_data: dict,
        resolution: ConflictResolution,
    ) -> MetadataVersion | None:
        if resolution == ConflictResolution.KEEP_EXISTING:
            return None
        if resolution == ConflictResolution.OVERWRITE:
            new_hash = MetadataHashCalculator.compute_hash(remote_data)
            return MetadataVersion.create(
                organization_id=local_version.organization_id,
                sync_job_id=local_version.sync_job_id,
                component_type=local_version.component_type,
                component_name=local_version.component_name,
                component_id=local_version.component_id,
                hash=new_hash,
                version_number=local_version.version_number + 1,
                action=MetadataAction.UPDATED,
                payload=remote_data,
                change_source="conflict_resolution",
            )
        return None
