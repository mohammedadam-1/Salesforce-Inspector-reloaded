"""Phase 5 Task 10 — real sync validation probe.

Mirrors the celery `metadata.full_sync` task path exactly (no celery):
  Container -> start_sync -> get_sync_job -> execute_sync
Runs against the existing (placeholder) connection in the database.
Intended to prove the real outbound path executes and fails cleanly
at OAuth when tokens are placeholders.

Usage: Agent.env/bin/python scripts/phase5_real_sync_probe.py
"""

import asyncio
import json
import sys
import traceback
import uuid

CONNECTION_ID = "c29977cf-ecff-47ff-ab24-286d10c2c21c"
ORGANIZATION_ID = "85962be2-e392-4a2d-b8b8-52a9338d898e"
SYNC_TYPE = "full"


def log(kind: str, message: str) -> None:
    print(f"[{kind}] {message}", flush=True)


async def main() -> int:
    from sfir_backend.application.dto.metadata_sync import StartSyncRequest
    from sfir_backend.config.container import Container
    from sfir_backend.config.settings import get_settings

    settings = get_settings()
    log("env", f"client_id={'SET' if settings.salesforce_client_id else 'MISSING'} "
               f"secret={'SET' if settings.salesforce_client_secret else 'MISSING'} "
               f"redirect={'SET' if settings.salesforce_redirect_uri else 'MISSING'} "
               f"database={'SET' if settings.database_url else 'MISSING'}")

    container = Container(settings)
    await container.startup()
    try:
        coordinator = container.get_use_case("sync_coordinator")
        request = StartSyncRequest(
            connection_id=uuid.UUID(CONNECTION_ID),
            sync_type=SYNC_TYPE,
        )
        log("api", f"start_sync(connection={CONNECTION_ID}, type={SYNC_TYPE})")
        response = await coordinator.start_sync(
            request, uuid.UUID(ORGANIZATION_ID),
        )
        log("api", f"job created id={response.id} status={response.status}")
        job = await coordinator.get_sync_job(response.id, uuid.UUID(ORGANIZATION_ID))
        log("api", f"job loaded status={job.status}")
        if job:
            from sfir_backend.domain.entities.metadata_sync import SyncJob
            from sfir_backend.domain.value_objects.metadata import SyncType

            sync_job = SyncJob(
                id=uuid.UUID(str(job.id)),
                organization_id=uuid.UUID(ORGANIZATION_ID),
                connection_id=uuid.UUID(CONNECTION_ID),
                sync_type=SyncType(SYNC_TYPE),
            )
            await coordinator.execute_sync(sync_job)
            job = sync_job
        log("api", f"execute_sync returned status={job.status}")
        if job.status == "completed":
            log("result", json.dumps({
                "status": job.status,
                "items_synced": job.items_synced,
                "completed_at": str(job.completed_at),
            }, default=str))
            return 0
        log("result", json.dumps({
            "status": job.status,
            "error": job.error_message,
            "progress": job.progress,
        }, default=str))
        return 2
    except Exception as exc:
        log("error", f"exception={type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stdout)
        return 3
    finally:
        await container.shutdown()
        log("env", "container shutdown complete")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
