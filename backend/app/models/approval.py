from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class ApprovalRequests(Base):
    __tablename__ = "approval_requests"

    approval_id = Column(String(50), primary_key=True)
    target_entity_type = Column(String(50), nullable=False, index=True)  # asset, model, kpi, artifact, migration
    target_entity_id = Column(String(50), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)  # RETIRE, CONSOLIDATE, MIGRATE, CHANGE_MODEL, CHANGE_KPI, PUBLISH_ARTIFACT, GOVERNANCE_EXCEPTION
    recommendation_ref = Column(String(100), nullable=True, index=True)  # reference to REC-xxx, ASM-xxx, or MIG-xxx
    requester_id = Column(String(100), nullable=False, index=True)
    requester_role = Column(String(50), nullable=False, default="REQUESTER")
    required_role = Column(String(50), nullable=False, index=True)  # BI_GOVERNANCE_REVIEWER, ASSET_OWNER, DOMAIN_STEWARD, BIOS_ADMIN
    status = Column(String(30), nullable=False, default="PENDING", index=True)  # DRAFT, PENDING, APPROVED, REJECTED, CHANGES_REQUESTED, CANCELLED, EXPIRED
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    evidence_snapshot_json = Column(Text, nullable=True)
    blockers_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    decision_reason = Column(Text, nullable=True)
    decided_by_id = Column(String(100), nullable=True)
    decided_by_role = Column(String(50), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    transitions = relationship("ApprovalStateTransitions", back_populates="approval", cascade="all, delete-orphan", order_by="ApprovalStateTransitions.transitioned_at")

    __table_args__ = (
        Index("ix_approval_status_role", "status", "required_role"),
        Index("ix_approval_target", "target_entity_type", "target_entity_id"),
    )


class ApprovalStateTransitions(Base):
    __tablename__ = "approval_state_transitions"

    transition_id = Column(String(50), primary_key=True)
    approval_id = Column(String(50), ForeignKey("approval_requests.approval_id", ondelete="CASCADE"), nullable=False, index=True)
    from_state = Column(String(30), nullable=False)
    to_state = Column(String(30), nullable=False)
    actor_id = Column(String(100), nullable=False)
    actor_role = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    transitioned_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    approval = relationship("ApprovalRequests", back_populates="transitions")


class AuditEvents(Base):
    """
    Append-only, immutable audit history log for all consequential lifecycle events,
    decisions, and governance actions.
    """
    __tablename__ = "audit_events"

    event_id = Column(String(50), primary_key=True)
    actor_id = Column(String(100), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # APPROVAL_REQUESTED, APPROVAL_GRANTED, APPROVAL_REJECTED, etc.
    target_entity_type = Column(String(50), nullable=False, index=True)
    target_entity_id = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    before_state_json = Column(Text, nullable=True)
    after_state_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    evidence_snapshot_json = Column(Text, nullable=True)
    associated_recommendation_id = Column(String(100), nullable=True, index=True)
    provenance_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("ix_audit_actor_event", "actor_id", "event_type"),
        Index("ix_audit_target_event", "target_entity_type", "target_entity_id"),
    )

