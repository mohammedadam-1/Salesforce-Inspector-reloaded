"""Celery worker entry point.

This module re-exports the Celery app instance so workers can be started with:

    celery -A sfir_backend.workers.celery worker --loglevel=info

Or with specific queues:

    celery -A sfir_backend.workers.celery worker -Q metadata,deployments
"""

from sfir_backend.infrastructure.queue.celery_app import celery_app

__all__ = ["celery_app"]
