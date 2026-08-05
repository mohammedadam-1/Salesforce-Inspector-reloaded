"""Deterministic batched retrieval of metadata type components.

Fetches components of a metadata type in cursor-based batches instead of
loading the entire type in one request. The batch cursor is the last
component key (Name) of the previous batch, so batches stay deterministic
and a sync can resume from any batch without an offset-based restart.
"""

import structlog

from sfir_backend.infrastructure.salesforce.sync.downloader import (
    MetadataDownloadError,
    MetadataDownloadManager,
)

logger = structlog.get_logger(__name__)


class MetadataBatchRetriever:
    """Cursor-paginates metadata components via SOQL key-range batches."""

    def __init__(
        self,
        downloader: MetadataDownloadManager,
        batch_size: int = 200,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._downloader = downloader
        self._batch_size = batch_size

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @staticmethod
    def build_soql(metadata_type: str, cursor: str | None, batch_size: int) -> str:
        """Build the deterministic SOQL for one batch.

        ``cursor`` is the last component Name of the previous batch; it
        selects the key-range following that record (resume token).
        """
        query = (
            f"SELECT Id, Name, LastModifiedDate FROM {metadata_type} "
            "WHERE Name != NULL"
        )
        if cursor:
            escaped = cursor.replace("'", "\\'")
            query += f" AND Name > '{escaped}'"
        query += f" ORDER BY Name LIMIT {batch_size}"
        return query

    @staticmethod
    def next_cursor(batch: list[dict]) -> str | None:
        """Resume token for the next batch: last Name of this batch."""
        if not batch:
            return None
        last = batch[-1]
        return last.get("Name") or last.get("name")

    async def fetch_batch(
        self, metadata_type: str, cursor: str | None = None,
    ) -> list[dict]:
        """Fetch one deterministic batch, returning at most batch_size rows.

        Raises MetadataDownloadError if the batch cannot be retrieved.
        """
        soql = self.build_soql(metadata_type, cursor, self._batch_size)
        try:
            return await self._downloader.query_metadata(soql)
        except Exception as exc:
            raise MetadataDownloadError(
                f"Failed to retrieve batch for {metadata_type}"
                f" cursor={cursor!r}: {exc}",
            ) from exc
