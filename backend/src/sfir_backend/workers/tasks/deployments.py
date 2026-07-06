"""Celery tasks for deployment operations."""

from sfir_backend.infrastructure.queue.celery_app import celery_app


@celery_app.task(
    name="deployments.validate",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def validate_deployment(self, deployment_id: str) -> dict:
    """Validate a deployment package against the target org."""
    raise NotImplementedError("To be implemented in Phase 5/7")


@celery_app.task(
    name="deployments.execute",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def execute_deployment(self, deployment_id: str) -> dict:
    """Execute a deployment to Salesforce."""
    raise NotImplementedError("To be implemented in Phase 5/7")


@celery_app.task(
    name="deployments.verify",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
    track_started=True,
)
def verify_deployment(self, deployment_id: str) -> dict:
    """Verify a deployment was successful."""
    raise NotImplementedError("To be implemented in Phase 5/7")


@celery_app.task(
    name="deployments.rollback",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def rollback_deployment(self, deployment_id: str) -> dict:
    """Rollback a deployment."""
    raise NotImplementedError("To be implemented in Phase 5/7")
