"""
Comprehensive test suite for BIOS Approval Management Database Integration,
Demo Data Population, and Role-Based Adjudication Workflow.
"""
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.approval import (
    ApprovalRequests,
    ApprovalStateTransitions,
    AuditEvents,
)
from backend.app.models.core import AnalyticsAssets, Owners
from backend.scripts.import_approval_demo_data import import_demo_data, DEFAULT_WORKBOOK
from backend.app.approvals.service import approval_service
from backend.app.approvals.schemas import (
    ApprovalDecisionPayload,
    UserRole,
    ApprovalStatus,
    ApprovalActionType,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_demo_import_and_idempotency(db):
    """Verify demo dataset imports correctly and is completely idempotent on repeated runs."""
    stats1 = import_demo_data(DEFAULT_WORKBOOK, db)
    assert stats1["imported"] + stats1["updated"] == 20
    assert stats1["statuses"]["PENDING"] == 11
    assert stats1["statuses"]["APPROVED"] == 4
    assert stats1["statuses"]["REJECTED"] == 2
    assert stats1["statuses"]["CHANGES_REQUESTED"] == 3

    # Idempotent re-run
    stats2 = import_demo_data(DEFAULT_WORKBOOK, db)
    assert stats2["imported"] == 0
    assert stats2["updated"] == 20

    # Verify count in database
    demo_count = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id.like("DEMO-APP-%")).count()
    assert demo_count == 20


def test_requester_personal_query_isolation(client, db):
    """Requester / Analyst must ONLY see their own submitted requests and cannot adjudicate."""
    headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}

    # 1. List approvals
    res = client.get("/api/v1/approvals", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 5
    for item in items:
        assert item["requester_id"] == "REQ-001"
        assert item["approval_id"] in ["DEMO-APP-001", "DEMO-APP-002", "DEMO-APP-006", "DEMO-APP-011", "DEMO-APP-016"]

    # 2. Scoped summary
    summary = client.get("/api/v1/approvals/summary", headers=headers).json()
    assert summary["total_pending"] == 4
    assert summary["total_approved"] == 1
    assert summary["total_rejected"] == 0
    assert summary["total_changes_requested"] == 0

    # 3. Accessing foreign approval detail is forbidden
    foreign_res = client.get("/api/v1/approvals/DEMO-APP-003", headers=headers)
    assert foreign_res.status_code == 403

    # 4. Requester cannot approve or reject
    approve_res = client.post(
        "/api/v1/approvals/DEMO-APP-001/approve",
        headers=headers,
        json={"actor_id": "REQ-001", "actor_role": "REQUESTER", "decision": "APPROVED", "reason": "Self approval attempt"},
    )
    assert approve_res.status_code == 403
    assert "Requesters/Analysts are not authorized" in approve_res.text


def test_asset_owner_scope_isolation(client, db):
    """Asset Owner can only see and adjudicate requests within their asset custody scope."""
    # OWN-001 owns AST-0014, AST-0130, AST-0222
    headers = {"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"}

    res = client.get("/api/v1/approvals?search=DEMO-APP", headers=headers)
    assert res.status_code == 200
    items = res.json()
    owned_assets = [a[0] for a in db.query(AnalyticsAssets.asset_id).filter(AnalyticsAssets.owner_id == "OWN-001").all()]

    # Every item returned must be an asset owned by OWN-001 or requested by OWN-001
    for item in items:
        assert item["target_entity_id"] in owned_assets or item["requester_id"] == "OWN-001"

    # Must include DEMO-APP-003 (target AST-0014) and DEMO-APP-020 (target AST-0222)
    demo_ids = [x["approval_id"] for x in items]
    assert "DEMO-APP-003" in demo_ids
    assert "DEMO-APP-020" in demo_ids

    # Foreign asset request (AST-0024 is owned by OWN-003) cannot be accessed by OWN-001
    foreign_res = client.get("/api/v1/approvals/DEMO-APP-001", headers=headers)
    assert foreign_res.status_code == 403


def test_domain_steward_authorization(client, db):
    """Domain Steward can view and adjudicate domain-scoped approval requests."""
    headers = {"X-Actor-Id": "OWN-003", "X-Actor-Role": "DOMAIN_STEWARD"}

    res = client.get("/api/v1/approvals?search=DEMO-APP", headers=headers)
    assert res.status_code == 200
    items = res.json()

    # DEMO-APP-005, DEMO-APP-012, DEMO-APP-018 require DOMAIN_STEWARD
    demo_ids = [x["approval_id"] for x in items]
    assert "DEMO-APP-005" in demo_ids
    assert "DEMO-APP-012" in demo_ids
    assert "DEMO-APP-018" in demo_ids


def test_governance_reviewer_enterprise_view(client, db):
    """BI Governance Reviewer sees enterprise queue across all roles."""
    headers = {"X-Actor-Id": "REV-001", "X-Actor-Role": "BI_GOVERNANCE_REVIEWER"}

    res = client.get("/api/v1/approvals?search=DEMO-APP&limit=100", headers=headers)
    assert res.status_code == 200
    items = res.json()
    demo_ids = [x["approval_id"] for x in items]
    assert len(demo_ids) == 20


def test_anti_self_approval_ban(db):
    """Requester cannot approve their own submission even if they hold reviewer credentials."""
    # Attempting to approve DEMO-APP-001 (requester is REQ-001) as REQ-001
    with pytest.raises(PermissionError) as exc_info:
        approval_service.approve_request(
            "DEMO-APP-001",
            ApprovalDecisionPayload(
                actor_id="REQ-001",
                actor_role=UserRole.ASSET_OWNER,
                decision=ApprovalStatus.APPROVED,
                reason="Attempting self approval",
            ),
            db,
        )
    assert "Self-approval prohibited" in str(exc_info.value)


def test_n4_inactive_owner_rejection(db):
    """N4 Control: Inactive owner cannot approve requests."""
    # Query an inactive owner or simulate one
    inactive_owner = db.query(Owners).filter(Owners.status != "active").first()
    if inactive_owner:
        with pytest.raises(PermissionError) as exc_info:
            approval_service.approve_request(
                "DEMO-APP-003",
                ApprovalDecisionPayload(
                    actor_id=inactive_owner.owner_id,
                    actor_role=UserRole.ASSET_OWNER,
                    decision=ApprovalStatus.APPROVED,
                    reason="Inactive owner approval attempt",
                ),
                db,
            )
        assert "Inactive owner" in str(exc_info.value)


def test_transitions_and_audit_events_created(client, db):
    """State transitions and immutable audit events must exist for demo records."""
    # Transitions for DEMO-APP-001 (PENDING)
    t1 = db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.approval_id == "DEMO-APP-001").all()
    assert len(t1) >= 1
    assert t1[0].from_state == "DRAFT"
    assert t1[0].to_state == "PENDING"

    # Transitions for DEMO-APP-006 (APPROVED)
    t6 = db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.approval_id == "DEMO-APP-006").all()
    assert len(t6) >= 2
    assert t6[1].from_state == "PENDING"
    assert t6[1].to_state == "APPROVED"
    assert t6[1].actor_id == "OWN-001"

    # Audit events
    audits = db.query(AuditEvents).filter(AuditEvents.event_id.like("AUD-DEMO-APP-%")).all()
    assert len(audits) >= 20

    # API history endpoint
    res = client.get("/api/v1/approvals/DEMO-APP-006/history")
    assert res.status_code == 200
    history = res.json()
    assert len(history) == 2
    assert history[0]["to_state"] == "PENDING"
    assert history[1]["to_state"] == "APPROVED"
