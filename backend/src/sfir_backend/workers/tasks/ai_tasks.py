"""Celery tasks for AI operations."""

from sfir_backend.infrastructure.queue.celery_app import celery_app


@celery_app.task(
    name="ai.generate_documentation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def generate_documentation(self, organization_id: str, component_ids: list[str]) -> dict:
    """Generate documentation for specified metadata components."""
    raise NotImplementedError("To be implemented in Phase 8")


@celery_app.task(
    name="ai.impact_analysis",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def impact_analysis(self, organization_id: str, component_id: str, change_description: str) -> dict:
    """Run AI-powered impact analysis for a proposed change."""
    raise NotImplementedError("To be implemented in Phase 8")
