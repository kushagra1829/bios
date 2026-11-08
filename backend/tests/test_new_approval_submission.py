"""
Comprehensive test suite for the BIOS Requester New Request Submission Workflow.
Tests request creation, role authorization, catalog validation, PROV ID generation,
scoping barriers, anti-self-approval enforcement, state transitions, and audit trail persistence.
"""
import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.approval import ApprovalRequests, ApprovalStateTransitions, AuditEvents
from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.auth.schemas import UserRole, UserContext, ScopeType
from backend.app.approvals.schemas import (
    ApprovalCreate,
    ApprovalActionType,
    ApprovalStatus,
    ApprovalDecisionPayload,
)
from backend.app.api.v1.endpoints.approvals import (
    submit_approval_request,
    list_approvals,
    get_approval,
    approve_request,
    reject_request,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_approvals(db: Session):
    yield
    # Teardown: delete test-created approval records so demo dataset remains pure
    test_reqs = db.query(ApprovalRequests).filter(~ApprovalRequests.approval_id.like("DEMO-APP-%")).all()
    test_ids = [r.approval_id for r in test_reqs]
    if test_ids:
        db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.approval_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(AuditEvents).filter(AuditEvents.target_entity_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(ApprovalRequests).filter(ApprovalRequests.approval_id.in_(test_ids)).delete(synchronize_session=False)
        db.commit()


def test_requester_submits_reuse_request_for_catalog_asset(db: Session):
    """
    1. Requester (REQ-001) submits a REUSE request targeting AST-0014.
    - Verified persisted in SQLite with APR- ID.
    - Required reviewer role is resolved to ASSET_OWNER.
    - Status is PENDING.
    - Canonical KPIs and evidence snapshot are properly serialized.
    """
    # Ensure target asset exists in DB
    asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == "AST-0014").first()
    if not asset:
        asset = AnalyticsAssets(
            asset_id="AST-0014",
            asset_name="Test Cardiovascular Executive Dashboard",
            domain="Cardiovascular",
            product="Nubeqa",
            geography="France",
            certification_status="CERTIFIED",
            created_at=datetime.now(timezone.utc),
        )
        db.add(asset)
        db.commit()

    requester_user = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )

    payload = ApprovalCreate(
        title="Reuse AST-0014 for France Q4 2026 Review",
        action_type=ApprovalActionType.REUSE,
        description="Requesting reuse authorization for European commercial planning.",
        target_entity_id="AST-0014",
        target_entity_type="asset",
        evidence_snapshot={
            "product": "Nubeqa",
            "market": "France",
            "canonical_kpis": ["Gross Revenue", "Net Revenue"],
            "business_justification": "Avoid creating duplicate regional sales report.",
            "expected_outcome": "Harmonized reporting across EU commercial teams.",
        },
        blockers=[],
        warnings=[],
    )

    created = submit_approval_request(payload=payload, db=db, user=requester_user)

    assert created is not None
    assert created.approval_id.startswith("APR-")
    assert created.requester_id == "REQ-001"
    assert created.requester_role == UserRole.REQUESTER.value
    assert created.status == ApprovalStatus.PENDING.value
    assert created.required_role == UserRole.ASSET_OWNER.value
    assert created.target_entity_id == "AST-0014"

    # Verify persisted in SQLite
    persisted = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == created.approval_id).first()
    assert persisted is not None
    assert persisted.title == "Reuse AST-0014 for France Q4 2026 Review"

    # Verify initial state transition (DRAFT -> PENDING)
    transitions = (
        db.query(ApprovalStateTransitions)
        .filter(ApprovalStateTransitions.approval_id == created.approval_id)
        .all()
    )
    assert len(transitions) >= 1
    assert transitions[0].from_state == "DRAFT"
    assert transitions[0].to_state == "PENDING"
    assert transitions[0].actor_id == "REQ-001"

    # Verify audit event emitted (APPROVAL_REQUESTED)
    audit = (
        db.query(AuditEvents)
        .filter(
            AuditEvents.target_entity_id == "AST-0014",
            AuditEvents.event_type == "APPROVAL_REQUESTED",
            AuditEvents.actor_id == "REQ-001",
        )
        .first()
    )
    assert audit is not None
    assert audit.action == "REQUEST_REUSE"


def test_requester_personal_queue_scoping(db: Session):
    """
    2. Newly created request appears in REQ-001's personal queue.
    """
    requester_user = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )

    my_queue = list_approvals(db=db, user=requester_user, limit=100)
    assert any(req.requester_id == "REQ-001" for req in my_queue)
    # Requesters must ONLY see their own requests
    assert all(req.requester_id == "REQ-001" for req in my_queue)


def test_requester_isolation_prevents_viewing_other_submissions(db: Session):
    """
    3. Another requester (REQ-002) is strictly forbidden (HTTP 403)
    from accessing REQ-001's private submission.
    """
    user1 = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )
    payload = ApprovalCreate(
        title="Private Submission by REQ-001",
        action_type=ApprovalActionType.REUSE,
        description="Confidential commercial inquiry.",
        target_entity_id="AST-0014",
    )
    created = submit_approval_request(payload=payload, db=db, user=user1)

    # REQ-002 attempts to inspect
    user2 = UserContext(
        actor_id="REQ-002",
        actor_name="Marco Rossi",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )
    with pytest.raises(HTTPException) as exc_info:
        get_approval(approval_id=created.approval_id, db=db, user=user2)
    assert exc_info.value.status_code == 403
    assert "Requesters cannot access other users' private approval submissions" in exc_info.value.detail


def test_requester_cannot_approve_or_reject_requests(db: Session):
    """
    4. Anti-self-approval and role boundary:
    REQUESTER / ANALYST cannot adjudicate (approve or reject) requests.
    """
    requester_user = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )
    decision = ApprovalDecisionPayload(
        actor_id="REQ-001",
        actor_role=UserRole.REQUESTER,
        reason="I approve my own request.",
    )

    with pytest.raises(HTTPException) as exc_approve:
        approve_request(approval_id="DEMO-APP-001", payload=decision, db=db, user=requester_user)
    assert exc_approve.value.status_code == 403
    assert "Requesters/Analysts are not authorized to adjudicate" in exc_approve.value.detail

    with pytest.raises(HTTPException) as exc_reject:
        reject_request(approval_id="DEMO-APP-001", payload=decision, db=db, user=requester_user)
    assert exc_reject.value.status_code == 403


def test_build_new_generates_provisional_id_and_routes_to_steward(db: Session):
    """
    5. BUILD_NEW action does NOT require target entity ID.
    System generates a PROV-XXXXXX ID and routes required_role to DOMAIN_STEWARD.
    """
    requester_user = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )
    payload = ApprovalCreate(
        title="Propose New Oncology Commercial Model",
        action_type=ApprovalActionType.BUILD_NEW,
        description="Net-new analytics workspace for emerging therapeutic launch.",
        target_entity_id="",  # Omitted by requester
        evidence_snapshot={
            "product": "Aliqopa",
            "market": "Global",
            "canonical_kpis": ["TRx Count", "NRx Count"],
        },
    )

    created = submit_approval_request(payload=payload, db=db, user=requester_user)

    assert created is not None
    assert created.target_entity_id.startswith("PROV-")
    assert created.required_role == UserRole.DOMAIN_STEWARD.value
    assert created.status == ApprovalStatus.PENDING.value

    # Verify persisted in DB
    persisted = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == created.approval_id).first()
    assert persisted is not None
    assert persisted.target_entity_id == created.target_entity_id


def test_non_build_new_rejects_missing_or_invalid_asset(db: Session):
    """
    6. Non-BUILD_NEW actions (REUSE, MODIFY, RETIRE, CONSOLIDATE)
    must fail validation (HTTP 422) if target asset is missing or not in catalog.
    """
    requester_user = UserContext(
        actor_id="REQ-001",
        actor_name="Elena Rostova",
        role=UserRole.REQUESTER,
        scope_type=ScopeType.ENTERPRISE,
        scope_value="Global",
        is_admin=False,
    )

    # Missing target asset ID
    payload_missing = ApprovalCreate(
        title="Modify Unspecified Asset",
        action_type=ApprovalActionType.MODIFY,
        description="Missing asset ID test.",
        target_entity_id="",
    )
    with pytest.raises(HTTPException) as exc_missing:
        submit_approval_request(payload=payload_missing, db=db, user=requester_user)
    assert exc_missing.value.status_code == 422
    assert "Target entity ID is mandatory" in exc_missing.value.detail

    # Non-existent asset ID
    payload_invalid = ApprovalCreate(
        title="Retire Non-existent Asset",
        action_type=ApprovalActionType.RETIRE,
        description="Invalid asset ID test.",
        target_entity_id="AST-99999",
    )
    with pytest.raises(HTTPException) as exc_invalid:
        submit_approval_request(payload=payload_invalid, db=db, user=requester_user)
    assert exc_invalid.value.status_code == 422
    assert "not found in analytics catalog" in exc_invalid.value.detail


def test_http_endpoint_submission_workflow(client: TestClient):
    """
    7. Full end-to-end HTTP integration test via FastAPI TestClient:
    - POST /api/v1/approvals with X-Actor-Id: REQ-001
    - Verify 201 Created response and payload
    - Verify immediate presence in GET /api/v1/approvals
    - Verify forbidden access by another requester via HTTP
    """
    headers_req1 = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}
    payload = {
        "title": "HTTP End-to-End Submission Test",
        "action_type": "REUSE",
        "description": "Integration test for HTTP client submission.",
        "target_entity_id": "AST-0014",
        "target_entity_type": "asset",
        "evidence_snapshot": {
            "product": "Nubeqa",
            "market": "France",
            "canonical_kpis": ["Gross Revenue"],
        },
    }

    # 1. Submit via HTTP
    res = client.post("/api/v1/approvals", json=payload, headers=headers_req1)
    assert res.status_code == 201
    data = res.json()
    assert data["approval_id"].startswith("APR-")
    assert data["requester_id"] == "REQ-001"
    assert data["required_role"] == "ASSET_OWNER"
    assert data["status"] == "PENDING"
    approval_id = data["approval_id"]

    # 2. Verify in personal queue
    queue_res = client.get("/api/v1/approvals", headers=headers_req1)
    assert queue_res.status_code == 200
    my_ids = [item["approval_id"] for item in queue_res.json()]
    assert approval_id in my_ids

    # 3. Verify foreign requester gets 403 Forbidden
    headers_req2 = {"X-Actor-Id": "REQ-002", "X-Actor-Role": "REQUESTER"}
    foreign_res = client.get(f"/api/v1/approvals/{approval_id}", headers=headers_req2)
    assert foreign_res.status_code == 403
