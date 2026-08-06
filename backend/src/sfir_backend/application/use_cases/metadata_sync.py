"""SyncCoordinator — orchestrates metadata synchronization."""

import contextlib
import uuid
from datetime import UTC, datetime

import structlog

from sfir_backend.application.dto.metadata_sync import (
    RetryQueueItemResponse,
    StartSyncRequest,
    SyncHistoryResponse,
    SyncJobResponse,
    SyncStatisticsResponse,
)
from sfir_backend.application.pipeline import MetadataPipeline, PipelineContext
from sfir_backend.domain.entities.metadata_sync import (
    MetadataVersion,
    SyncCheckpoint,
    SyncHistory,
    SyncJob,
    SyncStatistics,
)
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.canonical_relationship_repo import (
    ICanonicalRelationshipRepository,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.repositories.sync_repos import (
    IMetadataVersionRepository,
    ISyncCheckpointRepository,
    ISyncHistoryRepository,
    ISyncJobRepository,
    ISyncRetryQueueRepository,
    ISyncStatisticsRepository,
)
from sfir_backend.domain.value_objects.metadata import (
    KNOWN_METADATA_TYPES,
    BatchStatus,
    MetadataAction,
    SyncJobStatus,
    SyncType,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.salesforce.client import (
    SalesforceAuthError,
    SalesforceClient,
    SalesforceRateLimitError,
)
from sfir_backend.infrastructure.salesforce.oauth import SalesforceOAuthService
from sfir_backend.infrastructure.salesforce.sync.downloader import (
    MetadataDownloadError,
    MetadataDownloadManager,
)
from sfir_backend.infrastructure.salesforce.sync.manifest import (
    ManifestGenerator,
    MetadataChangeDetector,
    MetadataHashCalculator,
)
from sfir_backend.infrastructure.salesforce.sync.operations import (
    RetryManager,
    SyncProgressTracker,
    SyncRecovery,
    SyncStatusManager,
)
from sfir_backend.infrastructure.salesforce.sync.retriever import (
    MetadataBatchRetriever,
)
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.shared.exceptions.application import (
    ConflictError,
    RateLimitExceededError,
)
from sfir_backend.shared.exceptions.domain import EntityNotFoundError
from sfir_backend.shared.exceptions.infrastructure import SyncCancelledError

logger = structlog.get_logger(__name__)


class SyncCoordinator:
    """Orchestrates the full metadata synchronization lifecycle."""

    def __init__(
        self,
        connection_repo: ISalesforceConnectionRepository,
        sync_job_repo: ISyncJobRepository,
        version_repo: IMetadataVersionRepository,
        sync_history_repo: ISyncHistoryRepository,
        retry_repo: ISyncRetryQueueRepository,
        statistics_repo: ISyncStatisticsRepository,
        audit_log_repo: IAuditLogRepository,
        encryption_service: EncryptionService,
        download_manager: MetadataDownloadManager,
        hash_calculator: MetadataHashCalculator,
        change_detector: MetadataChangeDetector,
        manifest_generator: ManifestGenerator,
        retry_manager: RetryManager,
        recovery: SyncRecovery,
        oauth_service: SalesforceOAuthService,
        metadata_pipeline: MetadataPipeline | None = None,
        checkpoint_repo: ISyncCheckpointRepository | None = None,
        retriever: MetadataBatchRetriever | None = None,
        canonical_repo: ICanonicalDocumentRepository | None = None,
        canonical_relationship_repo: ICanonicalRelationshipRepository | None = None,
    ) -> None:
        self._connection_repo = connection_repo
        self._sync_job_repo = sync_job_repo
        self._version_repo = version_repo
        self._sync_history_repo = sync_history_repo
        self._retry_repo = retry_repo
        self._statistics_repo = statistics_repo
        self._audit_log_repo = audit_log_repo
        self._encryption = encryption_service
        self._downloader = download_manager
        self._hash_calculator = hash_calculator
        self._change_detector = change_detector
        self._manifest_generator = manifest_generator
        self._retry_manager = retry_manager
        self._recovery = recovery
        self._oauth_service = oauth_service
        self._pipeline = metadata_pipeline
        self._checkpoint_repo = checkpoint_repo
        self._retriever = retriever or MetadataBatchRetriever(download_manager)
        self._canonical_repo = canonical_repo
        self._canonical_relationship_repo = canonical_relationship_repo

    def _lock_key(self, org_id: uuid.UUID, conn_id: uuid.UUID) -> str:
        return f"sync_lock:{org_id}:{conn_id}"

    async def _acquire_lock(
        self, org_id: uuid.UUID, conn_id: uuid.UUID, ttl: int = 3600,
    ) -> bool:
        lock_key = self._lock_key(org_id, conn_id)
        try:
            from sfir_backend.infrastructure.cache.redis_cache import RedisCache
            cache = getattr(self, "_cache", None)
            if isinstance(cache, RedisCache) and cache._redis:
                locked = await cache._redis.set(lock_key, "1", nx=True, ex=ttl)
                return bool(locked)
        except Exception as exc:
            logger.warning("distributed_lock_unavailable", error=str(exc))
        return True

    async def _release_lock(self, org_id: uuid.UUID, conn_id: uuid.UUID) -> None:
        lock_key = self._lock_key(org_id, conn_id)
        try:
            from sfir_backend.infrastructure.cache.redis_cache import RedisCache
            cache = getattr(self, "_cache", None)
            if isinstance(cache, RedisCache) and cache._redis:
                await cache._redis.delete(lock_key)
        except Exception as exc:
            logger.warning("distributed_lock_release_failed", error=str(exc))

    async def start_sync(
        self,
        request: StartSyncRequest,
        organization_id: uuid.UUID,
        _user_id: uuid.UUID | None = None,
    ) -> SyncJobResponse:
        connection = await self._connection_repo.get_by_id(request.connection_id)
        if not connection or not connection.is_active:
            raise EntityNotFoundError(
                "SalesforceConnection", str(request.connection_id),
            )

        has_running = await self._sync_job_repo.has_running_job(
            organization_id, request.connection_id,
        )
        if has_running:
            raise ConflictError(
                "A sync job is already running for this connection",
            )

        sync_type = SyncType(request.sync_type)
        job = SyncJob.create(
            organization_id=organization_id,
            connection_id=request.connection_id,
            sync_type=sync_type,
            metadata_type=request.metadata_type,
        )
        await self._sync_job_repo.save(job)

        logger.info(
            "sync_job_created",
            job_id=str(job.id),
            sync_type=sync_type.value,
            connection_id=str(request.connection_id),
        )

        return self._job_to_response(job)

    async def execute_sync(self, job: SyncJob) -> SyncJob:
        """Execute a sync job with distributed lock + rate-limit handling."""
        if job.status == SyncJobStatus.CANCELLED:
            await self._record_sync_history(job, False)
            logger.info("sync_job_already_cancelled", job_id=str(job.id))
            return job

        locked = await self._acquire_lock(
            job.organization_id, job.connection_id,
        )
        if not locked:
            job.fail("Could not acquire distributed lock; another worker may be syncing")
            await self._sync_job_repo.update(job)
            await self._record_sync_history(job, False)
            return job

        job.start()
        await self._sync_job_repo.update(job)

        try:
            connection = await self._connection_repo.get_by_id(job.connection_id)
            if not connection:
                raise EntityNotFoundError(
                    "SalesforceConnection", str(job.connection_id),
                )

            access_token = self._encryption.decrypt(
                connection.access_token_encrypted,
            )

            client = SalesforceClient(
                instance_url=connection.instance_url,
                api_version=connection.api_version,
            )
            client.set_access_token(access_token)
            self._downloader.set_client(client)

            tracker = SyncProgressTracker(job, self._sync_job_repo.update)

            max_auth_retries = 2
            for attempt in range(max_auth_retries):
                self._check_cancelled(job)
                try:
                    if job.sync_type == SyncType.FULL:
                        await self._run_full_sync(job, tracker)
                    elif job.sync_type == SyncType.INCREMENTAL:
                        await self._run_incremental_sync(job, tracker)
                    elif job.sync_type == SyncType.RECOVERY:
                        await self._run_recovery_sync(job, tracker)
                    elif job.sync_type == SyncType.METADATA_TYPE and job.metadata_type:
                        await self._run_metadata_type_sync(job, tracker)
                    elif job.sync_type == SyncType.FORCE:
                        await self._run_forced_sync(job, tracker)
                    elif job.sync_type == SyncType.SCHEDULED:
                        await self._run_scheduled_sync(job, tracker)
                    elif job.sync_type == SyncType.MANUAL:
                        await self._run_manual_sync(job, tracker)
                    elif job.sync_type == SyncType.PARTIAL:
                        await self._run_partial_sync(job, tracker)
                    else:
                        await self._run_full_sync(job, tracker)
                    break
                except SalesforceAuthError:
                    if attempt >= max_auth_retries - 1:
                        raise
                    logger.info("sync_token_expired_refreshing", job_id=str(job.id))
                    await self._refresh_connection_token(connection)
                    new_token = self._encryption.decrypt(
                        connection.access_token_encrypted,
                    )
                    client.set_access_token(new_token)
                    self._downloader.set_client(client)

            await client.close()

            job.complete()
            await self._sync_job_repo.update(job)
            await self._record_sync_history(job, True)
            await self._update_statistics(job.organization_id, job.connection_id, True)

            logger.info(
                "sync_job_completed",
                job_id=str(job.id),
                processed=job.processed_items,
                failed=job.failed_items,
            )

        except SyncCancelledError:
            job.status = SyncJobStatus.CANCELLED
            job.updated_at = datetime.now(UTC)
            await self._sync_job_repo.update(job)
            await self._record_sync_history(job, False)
            logger.info("sync_job_cancelled", job_id=str(job.id))

        except (RateLimitExceededError, SalesforceRateLimitError) as exc:
            retry_after = getattr(exc, "retry_after", 60)
            if hasattr(exc, "context") and exc.context:
                retry_after = exc.context.get("retry_after", retry_after)
            job.fail(f"Rate limited; retry after {retry_after}s")
            await self._sync_job_repo.update(job)
            await self._record_sync_history(job, False)
            logger.warning("sync_rate_limited", job_id=str(job.id), retry_after=retry_after)

        except Exception as exc:
            job.fail(str(exc))
            await self._sync_job_repo.update(job)
            await self._record_sync_history(job, False)
            await self._update_statistics(
                job.organization_id, job.connection_id, False,
            )
            logger.error(
                "sync_job_failed",
                job_id=str(job.id),
                error=str(exc),
            )

        finally:
            await self._release_lock(job.organization_id, job.connection_id)

        return job

    @staticmethod
    def _check_cancelled(job: SyncJob) -> None:
        """Abort cooperatively if a cancellation was requested mid-run."""
        if job.status == SyncJobStatus.CANCELLED:
            raise SyncCancelledError(f"Sync job {job.id} was cancelled")

    async def execute_sync_by_id(
        self, job_id: uuid.UUID, organization_id: uuid.UUID,
    ) -> SyncJobResponse:
        """Load the persisted job and execute it (worker entry point).

        The persisted entity is used so status/progress/error state from a
        previous run (e.g. after resume) is honored instead of being reset.
        """
        job = await self._sync_job_repo.get_by_id(job_id)
        if not job or job.organization_id != organization_id:
            raise EntityNotFoundError("SyncJob", str(job_id))
        executed = await self.execute_sync(job)
        return self._job_to_response(executed)

    async def _refresh_connection_token(self, connection) -> None:
        refresh_token_encrypted = getattr(connection, "refresh_token_encrypted", "")
        if not refresh_token_encrypted:
            logger.warning("no_refresh_token_available")
            return
        try:
            refresh_token = self._encryption.decrypt(refresh_token_encrypted)
            env = SalesforceEnvironment(connection.environment)
            token_data = await self._oauth_service.refresh_access_token(
                refresh_token, environment=env,
            )
            new_access = token_data.get("access_token", "")
            new_refresh = token_data.get("refresh_token", "")
            if new_access:
                encrypted = self._encryption.encrypt(new_access)
                encrypted_refresh = self._encryption.encrypt(new_refresh) if new_refresh else None
                connection.update_tokens(
                    access_token_encrypted=encrypted,
                    refresh_token_encrypted=encrypted_refresh,
                    expires_in=int(token_data.get("expires_in") or 3600),
                )
                await self._connection_repo.update(connection)
                logger.info("salesforce_token_refreshed")
        except Exception as exc:
            logger.error("token_refresh_failed", error=str(exc))

    async def _run_full_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_types_sync(
            job, tracker, "full_sync",
            include_created=True,
            use_pipeline=self._pipeline is not None,
            abort_if_all_failed=True,
        )

    async def _run_types_sync(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        change_source: str,
        include_created: bool,
        use_pipeline: bool,
        abort_if_all_failed: bool,
    ) -> None:
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )
        await tracker.start(0)
        any_type_succeeded = False
        total = 0
        for mtype in KNOWN_METADATA_TYPES:
            self._check_cancelled(job)
            try:
                total += await self._sync_metadata_type_batched(
                    job, tracker, mtype, change_source,
                    old_versions, include_created, use_pipeline,
                )
                any_type_succeeded = True
            except SyncCancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "sync_metadata_type_failed",
                    metadata_type=mtype,
                    error=str(exc),
                )
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=mtype,
                    component_name="__batch__",
                    error=str(exc),
                )
                job.failed_items += 1

        if abort_if_all_failed and not any_type_succeeded and total == 0:
            raise MetadataDownloadError(
                "All metadata type queries failed; aborting sync to avoid "
                "false deletion of the existing manifest",
            )

    async def _sync_metadata_type_batched(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        metadata_type: str,
        change_source: str,
        old_versions: list[MetadataVersion],
        include_created: bool,
        use_pipeline: bool,
    ) -> int:
        """Retrieve one metadata type in deterministic batches.

        A checkpoint is persisted after every successful batch; a worker
        crash or restart resumes from the last checkpoint (a failed batch
        is retried from its cursor) instead of restarting from batch 1.
        """
        checkpoints = await self._checkpoint_repo.get_by_sync_job_and_type(
            job.id, metadata_type,
        )
        latest = checkpoints[-1] if checkpoints else None
        if latest is None:
            cursor: str | None = None
            batch_id = 1
            retry_count = 0
        elif latest.status == BatchStatus.FAILED:
            cursor = latest.cursor
            batch_id = latest.batch_id
            retry_count = latest.retry_count
        else:
            cursor = latest.cursor
            batch_id = latest.batch_id + 1
            retry_count = latest.retry_count

        fetched_names: set[str] = set()
        total = 0
        while True:
            self._check_cancelled(job)
            checkpoint = SyncCheckpoint.create(
                sync_job_id=job.id,
                organization_id=job.organization_id,
                metadata_type=metadata_type,
                batch_id=batch_id,
                cursor=cursor,
            )
            checkpoint.retry_count = retry_count
            try:
                batch = await self._retriever.fetch_batch(metadata_type, cursor)
                if not batch:
                    break
                components = [{"type": metadata_type, **c} for c in batch]
                for record in batch:
                    name = record.get("Name") or record.get("name")
                    if name:
                        fetched_names.add(name)
                next_cursor = self._retriever.next_cursor(batch)
                await self._process_batch_components(
                    job, tracker, metadata_type, components,
                    change_source, old_versions, include_created, use_pipeline,
                )
                checkpoint.cursor = next_cursor
                checkpoint.mark_completed()
                await self._checkpoint_repo.save(checkpoint)
                await tracker.add_total(len(components))
                total += len(components)
                if len(batch) < self._retriever.batch_size:
                    break
                cursor = next_cursor
                batch_id += 1
                retry_count = 0
            except SyncCancelledError:
                raise
            except Exception as exc:
                checkpoint.mark_failed()
                await self._checkpoint_repo.save(checkpoint)
                raise MetadataDownloadError(
                    f"Batch {batch_id} of {metadata_type} failed: {exc}",
                ) from exc

        if fetched_names:
            await self._persist_type_deletions(
                job, tracker, metadata_type, fetched_names,
                old_versions, change_source,
            )
        return total

    async def _process_batch_components(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        metadata_type: str,
        components: list[dict],
        change_source: str,
        old_versions: list[MetadataVersion],
        include_created: bool,
        use_pipeline: bool,
    ) -> None:
        manifest = self._manifest_generator.generate_manifest(
            components, component_type=metadata_type,
        )
        changes = self._change_detector.detect_changes(old_versions, manifest)
        live_changes = [
            c for c in changes
            if MetadataAction(c["action"]) != MetadataAction.DELETED
            and (include_created or MetadataAction(c["action"]) != MetadataAction.CREATED)
        ]
        if not live_changes:
            return
        if use_pipeline and self._pipeline:
            await self._pipeline_process_batches(
                job, tracker, live_changes, components, change_source,
            )
        else:
            await self._pipeline_process_batches_fallback(
                job, tracker, live_changes, components, old_versions, change_source,
            )

    async def _persist_type_deletions(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        metadata_type: str,
        fetched_names: set[str],
        old_versions: list[MetadataVersion],
        change_source: str,
    ) -> None:
        """Mark deletions only after the whole type was retrieved.

        Components persisted by this very job on a previous run are excluded
        so a resumed sync never produces false deletions.
        """
        for version in old_versions:
            if (
                version.component_type != metadata_type
                or version.sync_job_id == job.id
                or version.action == MetadataAction.DELETED
                or version.component_name in fetched_names
            ):
                continue
            try:
                new_version = MetadataVersion.create(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=metadata_type,
                    component_name=version.component_name,
                    component_id=version.component_id,
                    hash=version.hash,
                    version_number=self._next_version(
                        old_versions, metadata_type, version.component_name,
                    ),
                    action=MetadataAction.DELETED,
                    payload=None,
                    change_source=change_source,
                )
                await self._version_repo.save(new_version)
                await tracker.increment_processed()
            except Exception as exc:
                logger.warning(
                    "sync_deleted_component_failed",
                    component=version.component_name,
                    error=str(exc),
                )
                job.failed_items += 1
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=metadata_type,
                    component_name=version.component_name,
                    error=str(exc),
                )

        if self._canonical_repo is not None and fetched_names:
            try:
                await self._canonical_repo.soft_delete_missing(
                    job.organization_id,
                    metadata_type,
                    fetched_names,
                    sync_job_id=job.id,
                )
            except Exception as exc:
                logger.warning(
                    "canonical_soft_delete_failed",
                    metadata_type=metadata_type,
                    error=str(exc),
                )

        if (
            self._canonical_relationship_repo is not None
            and self._canonical_repo is not None
            and fetched_names
        ):
            try:
                docs = await self._canonical_repo.list_latest_by_type(
                    job.organization_id, metadata_type,
                )
                deleted_identities = {
                    doc.identity
                    for doc in docs
                    if not doc.is_deleted and doc.api_name not in fetched_names
                }
                if deleted_identities:
                    await self._canonical_relationship_repo.soft_delete_by_source_identities(
                        job.organization_id,
                        deleted_identities,
                        sync_job_id=job.id,
                    )
            except Exception as exc:
                logger.warning(
                    "canonical_relationship_soft_delete_failed",
                    metadata_type=metadata_type,
                    error=str(exc),
                )

    async def _pipeline_process_batches(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        changes: list[dict],
        all_components: list[dict],
        change_source: str,
    ) -> None:
        type_batches: dict[str, list[dict]] = {}
        for change in changes:
            ctype = change["component_type"]
            if ctype not in type_batches:
                type_batches[ctype] = []
            type_batches[ctype].append(change)

        for ctype, batch_changes in type_batches.items():
            self._check_cancelled(job)
            names = {c["component_name"] for c in batch_changes}
            raw_components = [
                c for c in all_components
                if c.get("type") == ctype
                and c.get("Name", c.get("name", "")) in names
            ]

            for rc in raw_components:
                cid = rc.get("Id", rc.get("id", ""))
                if cid:
                    with contextlib.suppress(Exception):
                        detail = await self._downloader.get_component_detail(ctype, cid)
                        rc.update(detail)

            try:
                ctx = PipelineContext(
                    organization_id=job.organization_id,
                    connection_id=job.connection_id,
                    sync_job_id=job.id,
                    component_type=ctype,
                    raw_components=raw_components,
                    sync_type="full",
                    change_source=change_source,
                )
                result = await self._pipeline.process_component(ctx)
                if result.success:
                    for _ in range(result.total_count):
                        await tracker.increment_processed()
                else:
                    job.failed_items += len(result.errors)
                    for err in result.errors:
                        logger.warning("pipeline_batch_failed", error=err)
            except Exception as exc:
                job.failed_items += len(batch_changes)
                logger.error("pipeline_batch_error", component_type=ctype, error=str(exc))
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=ctype,
                    component_name="__batch__",
                    error=str(exc),
                )

    async def _pipeline_process_batches_fallback(
        self,
        job: SyncJob,
        tracker: SyncProgressTracker,
        changes: list[dict],
        all_components: list[dict],
        old_versions: list[MetadataVersion],
        change_source: str,
    ) -> None:
        for change in changes:
            try:
                action = MetadataAction(change["action"])
                component_type = change["component_type"]
                component_name = change["component_name"]
                component_id = change.get("component_id", "")

                payload = None
                if component_id:
                    with contextlib.suppress(Exception):
                        payload = await self._downloader.get_component_detail(
                            component_type, component_id,
                        )

                version = MetadataVersion.create(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=component_type,
                    component_name=component_name,
                    component_id=component_id,
                    hash=change["hash"],
                    version_number=self._next_version(
                        old_versions, component_type, component_name,
                    ),
                    action=action,
                    payload=payload,
                    change_source=change_source,
                )
                await self._version_repo.save(version)
                await tracker.increment_processed()
            except Exception as exc:
                logger.warning(
                    "sync_component_failed",
                    component=change.get("component_name"),
                    error=str(exc),
                )
                job.failed_items += 1
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=change["component_type"],
                    component_name=change["component_name"],
                    error=str(exc),
                )

    async def _run_incremental_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_types_sync(
            job, tracker, "incremental_sync",
            include_created=True,
            use_pipeline=self._pipeline is not None,
            abort_if_all_failed=False,
        )

    async def _run_metadata_type_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        if not job.metadata_type:
            return
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )
        await tracker.start(0)
        try:
            await self._sync_metadata_type_batched(
                job, tracker, job.metadata_type, "metadata_type_sync",
                old_versions, include_created=True,
                use_pipeline=self._pipeline is not None,
            )
        except Exception as exc:
            logger.warning(
                "sync_metadata_type_failed",
                metadata_type=job.metadata_type,
                error=str(exc),
            )
            job.failed_items += 1
            await self._retry_manager.enqueue(
                organization_id=job.organization_id,
                sync_job_id=job.id,
                component_type=job.metadata_type,
                component_name="__batch__",
                error=str(exc),
            )

    async def _run_forced_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_types_sync(
            job, tracker, "forced_sync",
            include_created=True, use_pipeline=False,
            abort_if_all_failed=False,
        )

    async def _run_scheduled_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_types_sync(
            job, tracker, "scheduled_sync",
            include_created=False, use_pipeline=False,
            abort_if_all_failed=False,
        )

    async def _run_manual_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_full_sync(job, tracker)

    async def _run_partial_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        if job.metadata_type:
            old_versions = await self._version_repo.list_by_organization(
                job.organization_id, limit=100000,
            )
            await tracker.start(0)
            try:
                await self._sync_metadata_type_batched(
                    job, tracker, job.metadata_type, "partial_sync",
                    old_versions, include_created=True, use_pipeline=False,
                )
            except Exception as exc:
                logger.warning("partial_sync_failed", error=str(exc))
                job.failed_items += 1

    async def _run_recovery_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        retry_items = await self._retry_repo.list_by_sync_job(job.id)
        for item in retry_items:
            self._check_cancelled(job)
            if item.status.value in ("pending", "processing"):
                try:
                    payload = await self._downloader.get_component_detail(
                        item.component_type, item.component_name,
                    )
                    if payload:
                        await self._retry_manager.mark_completed(item)
                        await tracker.increment_processed()
                    else:
                        has_retry = await self._retry_manager.process_retry(item)
                        if not has_retry:
                            await tracker.increment_failed()
                except Exception:
                    has_retry = await self._retry_manager.process_retry(item)
                    if not has_retry:
                        await tracker.increment_failed()

    async def get_sync_job(
        self, job_id: uuid.UUID, organization_id: uuid.UUID,
    ) -> SyncJobResponse | None:
        job = await self._sync_job_repo.get_by_id(job_id)
        if not job or job.organization_id != organization_id:
            return None
        return self._job_to_response(job)

    async def list_sync_jobs(
        self, organization_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncJobResponse]:
        jobs = await self._sync_job_repo.list_by_organization(
            organization_id, limit=limit, offset=offset,
        )
        return [self._job_to_response(j) for j in jobs]

    async def cancel_sync(
        self, job_id: uuid.UUID, organization_id: uuid.UUID,
    ) -> SyncJobResponse:
        job = await self._sync_job_repo.get_by_id(job_id)
        if not job or job.organization_id != organization_id:
            raise EntityNotFoundError("SyncJob", str(job_id))
        if not SyncStatusManager.can_transition(job.status, SyncJobStatus.CANCELLED):
            raise ConflictError(f"Cannot cancel sync job in status {job.status.value}")
        SyncStatusManager.apply_transition(job, SyncJobStatus.CANCELLED)
        await self._sync_job_repo.update(job)
        return self._job_to_response(job)

    async def get_sync_history(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[SyncHistoryResponse]:
        if connection_id:
            history = await self._sync_history_repo.list_by_connection(
                connection_id, limit=limit, offset=offset,
            )
        else:
            history = await self._sync_history_repo.list_by_organization(
                organization_id, limit=limit, offset=offset,
            )
        return [self._history_to_response(h) for h in history]

    async def get_sync_statistics(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> SyncStatisticsResponse:
        stats = await self._statistics_repo.get_by_connection(
            organization_id, connection_id,
        )
        if not stats:
            stats = SyncStatistics.create(organization_id, connection_id)
            stats = await self._statistics_repo.save(stats)
        return self._stats_to_response(stats)

    async def get_retry_queue(
        self, organization_id: uuid.UUID, limit: int = 50,
    ) -> list[RetryQueueItemResponse]:
        items = await self._retry_manager.get_pending_items(
            organization_id, limit=limit,
        )
        return [self._retry_item_to_response(i) for i in items]

    async def pause_sync(
        self, job_id: uuid.UUID, organization_id: uuid.UUID,
    ) -> SyncJobResponse:
        job = await self._sync_job_repo.get_by_id(job_id)
        if not job or job.organization_id != organization_id:
            raise EntityNotFoundError("SyncJob", str(job_id))
        SyncStatusManager.apply_transition(job, SyncJobStatus.PAUSED)
        await self._sync_job_repo.update(job)
        return self._job_to_response(job)

    async def resume_sync(
        self, job_id: uuid.UUID, organization_id: uuid.UUID,
    ) -> SyncJobResponse:
        job = await self._sync_job_repo.get_by_id(job_id)
        if not job or job.organization_id != organization_id:
            raise EntityNotFoundError("SyncJob", str(job_id))
        can_resume = await self._recovery.can_resume(job)
        if not can_resume:
            raise ConflictError("Job cannot be resumed")
        job.status = SyncJobStatus.RUNNING
        await self._sync_job_repo.update(job)
        return self._job_to_response(job)

    async def _record_sync_history(self, job: SyncJob, _success: bool) -> None:
        history = SyncHistory.from_job(job)
        await self._sync_history_repo.save(history)

    async def _update_statistics(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID, success: bool,
    ) -> None:
        stats = await self._statistics_repo.get_by_connection(
            organization_id, connection_id,
        )
        if not stats:
            stats = SyncStatistics.create(organization_id, connection_id)
            stats = await self._statistics_repo.save(stats)
        stats.record_sync(success)
        await self._statistics_repo.update(stats)

    @staticmethod
    def _next_version(
        old_versions: list[MetadataVersion],
        component_type: str, component_name: str,
    ) -> int:
        return max(
            (v.version_number for v in old_versions
             if v.component_type == component_type
             and v.component_name == component_name),
            default=0,
        ) + 1

    @staticmethod
    def _job_to_response(job: SyncJob) -> SyncJobResponse:
        return SyncJobResponse(
            id=job.id,
            organization_id=job.organization_id,
            connection_id=job.connection_id,
            sync_type=job.sync_type.value,
            status=job.status.value,
            metadata_type=job.metadata_type,
            progress=job.progress,
            total_items=job.total_items,
            processed_items=job.processed_items,
            failed_items=job.failed_items,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _history_to_response(h: SyncHistory) -> SyncHistoryResponse:
        return SyncHistoryResponse(
            id=h.id,
            organization_id=h.organization_id,
            connection_id=h.connection_id,
            sync_type=h.sync_type.value,
            status=h.status.value,
            total_items=h.total_items,
            processed_items=h.processed_items,
            failed_items=h.failed_items,
            error_message=h.error_message,
            started_at=h.started_at,
            completed_at=h.completed_at,
            created_at=h.created_at,
        )

    @staticmethod
    def _stats_to_response(s: SyncStatistics) -> SyncStatisticsResponse:
        return SyncStatisticsResponse(
            id=s.id,
            organization_id=s.organization_id,
            connection_id=s.connection_id,
            total_syncs=s.total_syncs,
            successful_syncs=s.successful_syncs,
            failed_syncs=s.failed_syncs,
            total_components_synced=s.total_components_synced,
            total_components_created=s.total_components_created,
            total_components_updated=s.total_components_updated,
            total_components_deleted=s.total_components_deleted,
            last_sync_at=s.last_sync_at,
            last_successful_sync_at=s.last_successful_sync_at,
        )

    @staticmethod
    def _retry_item_to_response(i):
        return RetryQueueItemResponse(
            id=i.id,
            component_type=i.component_type,
            component_name=i.component_name,
            attempt_count=i.attempt_count,
            max_attempts=i.max_attempts,
            last_error=i.last_error,
            next_retry_at=i.next_retry_at,
            status=i.status.value,
        )
