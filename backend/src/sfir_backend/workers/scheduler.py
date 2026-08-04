"""Celery Beat schedule configuration.

Defines recurring tasks for metadata synchronization,
dependency graph rebuilds, and stale data detection.
"""

from celery.schedules import crontab

from sfir_backend.workers.celery import celery_app

celery_app.conf.beat_schedule = {
    "incremental-sync-hourly": {
        "task": "metadata.dispatch_scheduled_syncs",
        "schedule": crontab(minute=0),
        "args": ["incremental"],
        "options": {"queue": "default"},
    },
    "full-sync-daily": {
        "task": "metadata.dispatch_scheduled_syncs",
        "schedule": crontab(hour=2, minute=0),
        "args": ["full"],
        "options": {"queue": "default"},
    },
    "stale-detection-quarterly": {
        "task": "metadata.dispatch_stale_detection",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "default"},
    },
}
