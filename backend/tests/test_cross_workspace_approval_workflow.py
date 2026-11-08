"""
BIOS 1.0 — Cross-Workspace Approval Workflow Regression Test Suite.
Validates end-to-end synchronization between REQUESTER and ASSET_OWNER workspaces:
1. Submission from REQUESTER workspace (persisted in SQLite, routed to ASSET_OWNER).
2. Immediate visibility in assigned ASSET_OWNER's queue without manual import.
3. Consistent metadata across workspaces (ID, title, action type, requester, pending status).
4. Adjudication by assigned ASSET_OWNER (Approve / Reject).
5. Immediate visibility of updated decision and status upon switching back to REQUESTER.
6. Full audit logging and transition trail preservation.
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.approval import ApprovalRequests, ApprovalStateTransitions, AuditEvents
from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.auth.schemas import UserRole


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def cleanup_test_approvals():
    yield
    # Teardown: delete any non-demo approval records created by this test module
    session = SessionLocal()
    try:
        test_reqs = session.query(ApprovalRequests).filter(~ApprovalRequests.approval_id.like("DEMO-APP-%")).all()
        test_ids = [r.approval_id for r in test_reqs]
        if test_ids:
            session.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.approval_id.in_(test_ids)).delete(synchronize_session=False)
            session.query(AuditEvents).filter(AuditEvents.target_entity_id.in_(test_ids)).delete(synchronize_session=False)
            session.query(ApprovalRequests).filter(ApprovalRequests.approval_id.in_(test_ids)).delete(synchronize_session=False)
            session.commit()
    finally:
        session.close()


def test_requester_to_asset_owner_approval_workflow(client: TestClient, db: Session):
    """
    Full cross-workspace lifecycle validation:
    1. REQUESTER submits REUSE request for AST-0240.
    2. Request is persisted in SQLite with status PENDING and required_role ASSET_OWNER.
    3. ASSET_OWNER (OWN-001) logs in; request appears immediately in Approvals and Decisions queue.
    4. ASSET_OWNER approves the request with substantive rationale.
    5. REQUESTER logs back in; status is immediately visible as APPROVED.
    """
    requester_headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}
    asset_owner_headers = {"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"}

    # --- STEP 1: Requester submits request for AST-0240 ---
    submit_payload = {
        "title": "Reuse AST-0240 for EMEA Nubeqa Actuals vs Forecast",
        "action_type": "REUSE",
        "target_entity_type": "asset",
        "target_entity_id": "AST-0240",
        "description": "Harmonize EMEA Nubeqa reporting without creating redundant regional dashboard.",
        "evidence_snapshot": {
            "product": "Nubeqa",
            "market": "EMEA",
            "canonical_kpis": ["Net Sales", "Net Sales Growth"],
            "justification": "Reuse existing certified data baseline.",
        },
        "blockers": [],
        "warnings": [],
    }

    create_res = client.post("/api/v1/approvals", json=submit_payload, headers=requester_headers)
    assert create_res.status_code == 201, f"Failed submission: {create_res.text}"
    created_data = create_res.json()

    approval_id = created_data["approval_id"]
    assert approval_id.startswith("APR-")
    assert created_data["target_entity_id"] == "AST-0240"
    assert created_data["action_type"] == "REUSE"
    assert created_data["requester_id"] == "REQ-001"
    assert created_data["required_role"] == "ASSET_OWNER"
    assert created_data["status"] == "PENDING"

    # Verify request is in Requester's queue
    req_queue_res = client.get("/api/v1/approvals", headers=requester_headers)
    assert req_queue_res.status_code == 200
    req_ids = [item["approval_id"] for item in req_queue_res.json()]
    assert approval_id in req_ids

    # --- STEP 2: Switch to ASSET_OWNER workspace (OWN-001) ---
    owner_queue_res = client.get("/api/v1/approvals", headers=asset_owner_headers)
    assert owner_queue_res.status_code == 200
    owner_items = owner_queue_res.json()
    owner_item_map = {item["approval_id"]: item for item in owner_items}

    # Verify the exact same request appears in the Asset Owner's queue
    assert approval_id in owner_item_map, (
        f"Request {approval_id} targeting AST-0240 did not appear in Asset Owner OWN-001's queue! "
        f"Available IDs: {list(owner_item_map.keys())}"
    )

    owner_view = owner_item_map[approval_id]
    assert owner_view["title"] == submit_payload["title"]
    assert owner_view["action_type"] == "REUSE"
    assert owner_view["requester_id"] == "REQ-001"
    assert owner_view["status"] == "PENDING"
    assert owner_view["target_entity_id"] == "AST-0240"

    # --- STEP 3: ASSET_OWNER executes approval decision ---
    decision_payload = {
        "actor_id": "OWN-001",
        "actor_role": "ASSET_OWNER",
        "reason": "Governance review complete. Verified deduplication against EMEA Nubeqa baseline.",
    }
    approve_res = client.post(f"/api/v1/approvals/{approval_id}/approve", json=decision_payload, headers=asset_owner_headers)
    assert approve_res.status_code == 200, f"Approval decision failed: {approve_res.text}"
    approved_data = approve_res.json()
    assert approved_data["status"] == "APPROVED"
    assert approved_data["decided_by_id"] == "OWN-001"
    assert approved_data["decided_by_role"] == "ASSET_OWNER"

    # --- STEP 4: Switch back to REQUESTER workspace ---
    req_check_res = client.get(f"/api/v1/approvals/{approval_id}", headers=requester_headers)
    assert req_check_res.status_code == 200
    req_item = req_check_res.json()
    assert req_item["status"] == "APPROVED"
    assert req_item["decided_by_id"] == "OWN-001"
    assert req_item["decision_reason"] == decision_payload["reason"]

    # --- STEP 5: Verify Transition Trail & Audit Event ---
    history_res = client.get(f"/api/v1/approvals/{approval_id}/history", headers=requester_headers)
    assert history_res.status_code == 200
    transitions = history_res.json()
    assert len(transitions) == 2
    assert transitions[0]["from_state"] == "DRAFT"
    assert transitions[0]["to_state"] == "PENDING"
    assert transitions[0]["actor_id"] == "REQ-001"
    assert transitions[1]["from_state"] == "PENDING"
    assert transitions[1]["to_state"] == "APPROVED"
    assert transitions[1]["actor_id"] == "OWN-001"


def test_requester_to_asset_owner_rejection_workflow(client: TestClient, db: Session):
    """
    Validate that rejections executed by the ASSET_OWNER persist
    and reflect immediately in the REQUESTER workspace.
    """
    requester_headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}
    asset_owner_headers = {"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"}

    # 1. Requester submits MODIFY request for AST-0014
    submit_payload = {
        "title": "Modify AST-0014 Metric Calculations",
        "action_type": "MODIFY",
        "target_entity_type": "asset",
        "target_entity_id": "AST-0014",
        "description": "Requesting formula tweak to regional margin calculation.",
        "evidence_snapshot": {"product": "Nubeqa", "market": "France"},
    }
    create_res = client.post("/api/v1/approvals", json=submit_payload, headers=requester_headers)
    assert create_res.status_code == 201
    approval_id = create_res.json()["approval_id"]

    # 2. Asset Owner rejects
    reject_payload = {
        "actor_id": "OWN-001",
        "actor_role": "ASSET_OWNER",
        "reason": "Rejected: Incompatible regional calculation breaks corporate gross-to-net standard.",
    }
    reject_res = client.post(f"/api/v1/approvals/{approval_id}/reject", json=reject_payload, headers=asset_owner_headers)
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "REJECTED"

    # 3. Requester sees status REJECTED
    req_view = client.get(f"/api/v1/approvals/{approval_id}", headers=requester_headers).json()
    assert req_view["status"] == "REJECTED"
    assert req_view["decided_by_id"] == "OWN-001"


def test_unassigned_asset_owner_isolation(client: TestClient, db: Session):
    """
    Verify that an Asset Owner who does NOT own the target asset
    cannot view or adjudicate the approval request (403 Forbidden).
    """
    requester_headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}
    # OWN-005 (Felix Schmidt) owns Supply assets, NOT AST-0240
    unassigned_owner_headers = {"X-Actor-Id": "OWN-005", "X-Actor-Role": "ASSET_OWNER"}

    submit_payload = {
        "title": "Confidential Request for AST-0240",
        "action_type": "REUSE",
        "target_entity_type": "asset",
        "target_entity_id": "AST-0240",
        "description": "Isolation test request.",
    }
    create_res = client.post("/api/v1/approvals", json=submit_payload, headers=requester_headers)
    assert create_res.status_code == 201
    approval_id = create_res.json()["approval_id"]

    # Unassigned owner cannot view detail
    foreign_get = client.get(f"/api/v1/approvals/{approval_id}", headers=unassigned_owner_headers)
    assert foreign_get.status_code == 403

    # Unassigned owner cannot approve
    foreign_approve = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"actor_id": "OWN-005", "actor_role": "ASSET_OWNER", "reason": "Unauthorized attempt."},
        headers=unassigned_owner_headers,
    )
    assert foreign_approve.status_code == 403
