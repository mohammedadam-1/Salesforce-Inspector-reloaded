"""Celery Beat schedule configuration.

Defines recurring tasks for metadata synchronization,
dependency graph rebuilds, and stale data detection.
"""

from celery.schedules import crontab

from sfir_backend.workers.celery import celery_app

celery_app.conf.beat_schedule = {
    "incremental-sync-hourly": {
        "task": "metadata.incremental_sync",
        "schedule": crontab(minute=0),
        "options": {"queue": "metadata"},
    },
    "full-sync-daily": {
        "task": "metadata.full_sync",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "metadata"},
    },
    "stale-detection-quarterly": {
        "task": "metadata.detect_stale",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "default"},
    },
}
