"""SyncCoordinator — orchestrates metadata synchronization."""

import contextlib
import uuid

import structlog

from sfir_backend.application.dto.metadata_sync import (
    RetryQueueItemResponse,
    StartSyncRequest,
    SyncHistoryResponse,
    SyncJobResponse,
    SyncStatisticsResponse,
)
from sfir_backend.domain.entities.metadata_sync import (
    MetadataVersion,
    SyncHistory,
    SyncJob,
    SyncStatistics,
)
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.repositories.sync_repos import (
    IMetadataVersionRepository,
    ISyncHistoryRepository,
    ISyncJobRepository,
    ISyncRetryQueueRepository,
    ISyncStatisticsRepository,
)
from sfir_backend.domain.value_objects.metadata import (
    KNOWN_METADATA_TYPES,
    MetadataAction,
    SyncJobStatus,
    SyncType,
)
from sfir_backend.infrastructure.salesforce.client import (
    SalesforceClient,
    SalesforceRateLimitError,
)
from sfir_backend.infrastructure.salesforce.sync.downloader import (
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
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.shared.exceptions.application import (
    ConflictError,
    RateLimitExceededError,
)
from sfir_backend.shared.exceptions.domain import EntityNotFoundError

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
        except Exception:
            pass
        return True

    async def _release_lock(self, org_id: uuid.UUID, conn_id: uuid.UUID) -> None:
        lock_key = self._lock_key(org_id, conn_id)
        try:
            from sfir_backend.infrastructure.cache.redis_cache import RedisCache
            cache = getattr(self, "_cache", None)
            if isinstance(cache, RedisCache) and cache._redis:
                await cache._redis.delete(lock_key)
        except Exception:
            pass

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

    async def _run_full_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        all_components: list[dict] = []
        for mtype in KNOWN_METADATA_TYPES:
            try:
                components = await self._downloader.get_metadata_components(mtype)
                all_components.extend(
                    {"type": mtype, **c} for c in components
                )
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

        await tracker.start(len(all_components))
        manifest = self._manifest_generator.generate_manifest(all_components)

        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )

        changes = self._change_detector.detect_changes(old_versions, manifest)

        for change in changes:
            try:
                action = MetadataAction(change["action"])
                component_type = change["component_type"]
                component_name = change["component_name"]
                component_id = change.get("component_id", "")

                if action == MetadataAction.DELETED:
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
                        payload=None,
                        change_source="full_sync",
                    )
                    await self._version_repo.save(version)
                    await tracker.increment_processed()
                    continue

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
                    change_source="full_sync",
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
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )

        all_components: list[dict] = []
        for mtype in KNOWN_METADATA_TYPES:
            try:
                components = await self._downloader.get_metadata_components(mtype)
                all_components.extend(
                    {"type": mtype, **c} for c in components
                )
            except Exception:
                continue

        await tracker.start(len(all_components))
        manifest = self._manifest_generator.generate_manifest(all_components)
        changes = self._change_detector.detect_changes(old_versions, manifest)

        for change in changes:
            try:
                action = MetadataAction(change["action"])
                if action == MetadataAction.DELETED:
                    version = MetadataVersion.create(
                        organization_id=job.organization_id,
                        sync_job_id=job.id,
                        component_type=change["component_type"],
                        component_name=change["component_name"],
                        component_id=change.get("component_id", ""),
                        hash=change["hash"],
                        version_number=self._next_version(
                            old_versions, change["component_type"], change["component_name"],
                        ),
                        action=action,
                        payload=None,
                        change_source="incremental_sync",
                    )
                    await self._version_repo.save(version)
                    await tracker.increment_processed()
                    continue

                component_id = change.get("component_id", "")
                payload = None
                if component_id:
                    with contextlib.suppress(Exception):
                        payload = await self._downloader.get_component_detail(
                            change["component_type"], component_id,
                        )

                version = MetadataVersion.create(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=change["component_type"],
                    component_name=change["component_name"],
                    component_id=component_id,
                    hash=change["hash"],
                    version_number=self._next_version(
                        old_versions, change["component_type"], change["component_name"],
                    ),
                    action=action,
                    payload=payload,
                    change_source="incremental_sync",
                )
                await self._version_repo.save(version)
                await tracker.increment_processed()

            except Exception as exc:
                job.failed_items += 1
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=change["component_type"],
                    component_name=change["component_name"],
                    error=str(exc),
                )

    async def _run_metadata_type_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        if not job.metadata_type:
            return
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )
        components = await self._downloader.get_metadata_components(job.metadata_type)
        all_components = [{"type": job.metadata_type, **c} for c in components]

        await tracker.start(len(all_components))
        manifest = self._manifest_generator.generate_manifest(
            all_components, component_type=job.metadata_type,
        )
        changes = self._change_detector.detect_changes(old_versions, manifest)

        for change in changes:
            try:
                action = MetadataAction(change["action"])
                payload = None
                component_id = change.get("component_id", "")
                if component_id and action != MetadataAction.DELETED:
                    with contextlib.suppress(Exception):
                        payload = await self._downloader.get_component_detail(
                            job.metadata_type, component_id,
                        )

                version = MetadataVersion.create(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=job.metadata_type,
                    component_name=change["component_name"],
                    component_id=component_id,
                    hash=change["hash"],
                    version_number=self._next_version(
                        old_versions, job.metadata_type, change["component_name"],
                    ),
                    action=action,
                    payload=payload,
                    change_source="metadata_type_sync",
                )
                await self._version_repo.save(version)
                await tracker.increment_processed()

            except Exception as exc:
                job.failed_items += 1
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=job.metadata_type,
                    component_name=change["component_name"],
                    error=str(exc),
                )

    async def _run_forced_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        all_components: list[dict] = []
        for mtype in KNOWN_METADATA_TYPES:
            try:
                components = await self._downloader.get_metadata_components(mtype)
                all_components.extend(
                    {"type": mtype, **c} for c in components
                )
            except Exception as exc:
                logger.warning(
                    "forced_sync_type_failed", metadata_type=mtype, error=str(exc),
                )
                await self._retry_manager.enqueue(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=mtype,
                    component_name="__batch__",
                    error=str(exc),
                )
                job.failed_items += 1

        await tracker.start(len(all_components))
        manifest = self._manifest_generator.generate_manifest(all_components)
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )
        changes = self._change_detector.detect_changes(old_versions, manifest)

        for change in changes:
            try:
                action = MetadataAction(change["action"])
                component_type = change["component_type"]
                component_name = change["component_name"]
                component_id = change.get("component_id", "")

                payload = None
                if component_id and action != MetadataAction.DELETED:
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
                    change_source="forced_sync",
                )
                await self._version_repo.save(version)
                await tracker.increment_processed()
            except Exception as exc:
                logger.warning("forced_sync_component_failed", error=str(exc))
                job.failed_items += 1

    async def _run_scheduled_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        old_versions = await self._version_repo.list_by_organization(
            job.organization_id, limit=100000,
        )
        all_components: list[dict] = []
        for mtype in KNOWN_METADATA_TYPES:
            try:
                components = await self._downloader.get_metadata_components(mtype)
                all_components.extend({"type": mtype, **c} for c in components)
            except Exception:
                continue

        await tracker.start(len(all_components))
        manifest = self._manifest_generator.generate_manifest(all_components)
        changes = self._change_detector.detect_changes(old_versions, manifest)

        only_updates = [c for c in changes if c.get("action") != "created"]
        for change in only_updates:
            try:
                action = MetadataAction(change["action"])
                component_id = change.get("component_id", "")
                payload = None
                if component_id and action != MetadataAction.DELETED:
                    with contextlib.suppress(Exception):
                        payload = await self._downloader.get_component_detail(
                            change["component_type"], component_id,
                        )
                version = MetadataVersion.create(
                    organization_id=job.organization_id,
                    sync_job_id=job.id,
                    component_type=change["component_type"],
                    component_name=change["component_name"],
                    component_id=component_id,
                    hash=change["hash"],
                    version_number=self._next_version(
                        old_versions, change["component_type"], change["component_name"],
                    ),
                    action=action,
                    payload=payload,
                    change_source="scheduled_sync",
                )
                await self._version_repo.save(version)
                await tracker.increment_processed()
            except Exception as exc:
                job.failed_items += 1
                logger.warning("scheduled_sync_failed", error=str(exc))

    async def _run_manual_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        await self._run_full_sync(job, tracker)

    async def _run_partial_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        if job.metadata_type:
            all_components: list[dict] = []
            try:
                components = await self._downloader.get_metadata_components(
                    job.metadata_type,
                )
                all_components = [{"type": job.metadata_type, **c} for c in components]
            except Exception as exc:
                logger.warning("partial_sync_failed", error=str(exc))
                job.failed_items += 1
                return

            await tracker.start(len(all_components))
            manifest = self._manifest_generator.generate_manifest(
                all_components, component_type=job.metadata_type,
            )
            old_versions = await self._version_repo.list_by_organization(
                job.organization_id, limit=100000,
            )
            changes = self._change_detector.detect_changes(old_versions, manifest)
            for change in changes:
                try:
                    action = MetadataAction(change["action"])
                    component_id = change.get("component_id", "")
                    payload = None
                    if component_id and action != MetadataAction.DELETED:
                        with contextlib.suppress(Exception):
                            payload = await self._downloader.get_component_detail(
                                job.metadata_type, component_id,
                            )
                    version = MetadataVersion.create(
                        organization_id=job.organization_id,
                        sync_job_id=job.id,
                        component_type=job.metadata_type,
                        component_name=change["component_name"],
                        component_id=component_id,
                        hash=change["hash"],
                        version_number=self._next_version(
                            old_versions, job.metadata_type, change["component_name"],
                        ),
                        action=action,
                        payload=payload,
                        change_source="partial_sync",
                    )
                    await self._version_repo.save(version)
                    await tracker.increment_processed()
                except Exception as exc:
                    job.failed_items += 1
                    await self._retry_manager.enqueue(
                        organization_id=job.organization_id,
                        sync_job_id=job.id,
                        component_type=job.metadata_type,
                        component_name=change["component_name"],
                        error=str(exc),
                    )

    async def _run_recovery_sync(
        self, job: SyncJob, tracker: SyncProgressTracker,
    ) -> None:
        retry_items = await self._retry_repo.list_by_sync_job(job.id)
        for item in retry_items:
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
        stats.record_components(
            created=stats.total_components_created,
            updated=stats.total_components_updated,
            deleted=stats.total_components_deleted,
        )
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
