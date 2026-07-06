"""Celery tasks for dependency graph operations."""

from sfir_backend.infrastructure.queue.celery_app import celery_app


@celery_app.task(
    name="dependency_graph.update_for_component",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def update_dependency_graph_for_component(self, organization_id: str, component_id: str) -> dict:
    """Update dependency edges for a single component."""
    raise NotImplementedError("To be implemented in Phase 7")


@celery_app.task(
    name="dependency_graph.full_rebuild",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    track_started=True,
)
def full_dependency_graph_rebuild(self, organization_id: str) -> dict:
    """Rebuild the entire dependency graph for an organization."""
    raise NotImplementedError("To be implemented in Phase 7")
