"""Celery application configuration.

Workers are configured via settings and connected to Redis as
both the broker and result backend.
"""

import structlog
from celery import Celery

from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

celery_app = Celery(
    "sfir_backend",
    broker=settings.celery_broker_url.get_secret_value(),
    backend=settings.celery_result_backend.get_secret_value(),
    include=[
        "sfir_backend.workers.tasks.metadata_sync",
        "sfir_backend.workers.tasks.dependency_rebuild",
        "sfir_backend.workers.tasks.ai_generation",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=3600,
    task_time_limit=3900,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=86400,
    beat_schedule_filename="/tmp/celerybeat-schedule",
)
