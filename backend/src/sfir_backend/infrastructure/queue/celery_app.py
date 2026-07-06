"""Celery application configuration."""

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger

from sfir_backend.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "sfir_backend",
    broker=settings.celery_broker_url.get_secret_value(),
    backend=settings.celery_result_backend.get_secret_value(),
    include=[
        "sfir_backend.workers.tasks.metadata_sync",
        "sfir_backend.workers.tasks.dependency_graph",
        "sfir_backend.workers.tasks.ai_tasks",
        "sfir_backend.workers.tasks.deployments",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_store_errors_even_if_ignored=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_max_memory_per_child=200_000,
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "metadata": {"exchange": "metadata", "routing_key": "metadata"},
        "deployments": {"exchange": "deployments", "routing_key": "deployments"},
        "ai": {"exchange": "ai", "routing_key": "ai"},
    },
    task_default_exchange="default",
    task_default_routing_key="default",
    task_routes={
        "sfir_backend.workers.tasks.metadata_sync.*": {"queue": "metadata"},
        "sfir_backend.workers.tasks.dependency_graph.*": {"queue": "metadata"},
        "sfir_backend.workers.tasks.deployments.*": {"queue": "deployments"},
        "sfir_backend.workers.tasks.ai_tasks.*": {"queue": "ai"},
    },
    task_soft_time_limit=300,
    task_time_limit=600,
    task_acks_on_failure_or_timeout=True,
    result_expires=86400,
    broker_connection_retry_on_startup=True,
)


@after_setup_logger.connect
def setup_celery_logger(logger, *args, **kwargs):
    """Configure Celery to use structured logging."""
    import logging
    import sys

    from sfir_backend.infrastructure.observability.logging import configure_logging

    configure_logging(settings)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)


@after_setup_task_logger.connect
def setup_celery_task_logger(logger, *args, **kwargs):
    """Configure Celery task logger."""
    import logging
    import sys

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
