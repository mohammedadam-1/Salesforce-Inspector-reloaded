import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ActionPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "action_plans"
    __table_args__ = (Index("ix_action_plans_org_status", "organization_id", "status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    summary: Mapped[str | None] = mapped_column(Text)
    plan_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    safety_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    rollback_plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class ActionStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "action_steps"
    __table_args__ = (Index("ix_action_steps_plan_order", "action_plan_id", "step_order"),)

    action_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    diff_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_action_status", "action_plan_id", "status"),)

    action_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deployments_org_status", "organization_id", "status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    action_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_plans.id", ondelete="SET NULL")
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    salesforce_deploy_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    check_only: Mapped[bool] = mapped_column(default=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text)


class DeploymentArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployment_artifacts"
    __table_args__ = (Index("ix_deployment_artifacts_deployment_kind", "deployment_id", "artifact_kind"),)

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    artifact_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    checksum: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class DeploymentVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployment_verifications"
    __table_args__ = (Index("ix_deployment_verifications_deployment", "deployment_id", "status"),)

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

