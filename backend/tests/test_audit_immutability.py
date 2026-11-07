import pytest
from backend.app.db.session import SessionLocal
from backend.app.approvals.service import approval_service
from backend.app.approvals.schemas import (
    ApprovalCreate,
    ApprovalDecisionPayload,
    ApprovalActionType,
    UserRole,
)
from backend.app.models.approval import AuditEvents


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_audit_log_appended_on_lifecycle_events(db):
    initial_event_count = db.query(AuditEvents).count()

    # 1. Create request -> APPROVAL_REQUESTED
    payload = ApprovalCreate(
        target_entity_type="asset",
        target_entity_id="AST-0010",
        action_type=ApprovalActionType.CONSOLIDATE,
        requester_id="user_requester_1",
        requester_role=UserRole.REQUESTER,
        title="Consolidate AST-0010",
        description="Consolidate duplicate variant into target model",
        evidence_snapshot={"asset_name": "AST-0010 Duplicate"},
    )
    approval = approval_service.create_request(payload, db)

    post_create_count = db.query(AuditEvents).count()
    assert post_create_count == initial_event_count + 1

    last_event = db.query(AuditEvents).order_by(AuditEvents.created_at.desc()).first()
    assert last_event.event_type == "APPROVAL_REQUESTED"
    assert last_event.actor_id == "user_requester_1"
    assert last_event.target_entity_id == "AST-0010"

    # 2. Reject request -> APPROVAL_REJECTED
    decision = ApprovalDecisionPayload(
        actor_id="reviewer_george",
        actor_role=UserRole.BI_GOVERNANCE_REVIEWER,
        reason="Consolidation scope is insufficient; needs user notification.",
    )
    approval_service.reject_request(approval.approval_id, decision, db)

    post_reject_count = db.query(AuditEvents).count()
    assert post_reject_count == post_create_count + 1

    reject_event = db.query(AuditEvents).order_by(AuditEvents.created_at.desc()).first()
    assert reject_event.event_type == "APPROVAL_REJECTED"
    assert reject_event.actor_id == "reviewer_george"
    assert reject_event.reason == decision.reason

