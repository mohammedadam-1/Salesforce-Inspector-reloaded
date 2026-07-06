"""Celery Beat schedule configuration.

Starts with:
    celery -A sfir_backend.workers.celery beat --loglevel=info
"""

from celery.schedules import crontab

from sfir_backend.infrastructure.queue.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "incremental-metadata-sync-every-hour": {
        "task": "metadata_sync.incremental_sync",
        "schedule": crontab(minute=0),
        "kwargs": {},
        "options": {"queue": "metadata"},
    },
    "full-metadata-sync-daily": {
        "task": "metadata_sync.full_sync",
        "schedule": crontab(hour=2, minute=0),
        "kwargs": {},
        "options": {"queue": "metadata"},
    },
    "dependency-graph-cleanup-daily": {
        "task": "dependency_graph.full_rebuild",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {},
        "options": {"queue": "metadata"},
    },
}
