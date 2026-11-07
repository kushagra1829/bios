from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_api_submit_and_approve_workflow():
    # 1. Submit approval request
    payload = {
        "target_entity_type": "asset",
        "target_entity_id": "AST-0050",
        "action_type": "CONSOLIDATE",
        "requester_id": "analyst_maria",
        "requester_role": "REQUESTER",
        "title": "Consolidate AST-0050 into shared model",
        "description": "Deduplicate regional dashboard into central model.",
        "evidence_snapshot": {"views": 120, "is_cross_domain": False},
        "blockers": [],
        "warnings": [],
    }
    create_res = client.post("/api/v1/approvals", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["status"] == "PENDING"
    approval_id = data["approval_id"]

    # 2. Self-approval attempt should fail with 403 Forbidden
    self_approve_payload = {
        "actor_id": "analyst_maria",
        "actor_role": "BI_GOVERNANCE_REVIEWER",
        "reason": "I approve my own request.",
    }
    self_res = client.post(f"/api/v1/approvals/{approval_id}/approve", json=self_approve_payload)
    assert self_res.status_code == 403

    # 3. Legitimate approval by designated reviewer
    approve_payload = {
        "actor_id": "reviewer_sarah",
        "actor_role": "BI_GOVERNANCE_REVIEWER",
        "reason": "Authorized: Deduplication verified against target model.",
    }
    appr_res = client.post(f"/api/v1/approvals/{approval_id}/approve", json=approve_payload)
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"
    assert appr_res.json()["decided_by_id"] == "reviewer_sarah"

    # 4. Attempt to re-approve already approved request should fail with 422 Unprocessable
    re_appr_res = client.post(f"/api/v1/approvals/{approval_id}/approve", json=approve_payload)
    assert re_appr_res.status_code == 422


def test_api_request_changes_and_rejection():
    # Submit request
    payload = {
        "target_entity_type": "kpi",
        "target_entity_id": "KPI-002",
        "action_type": "CHANGE_KPI",
        "requester_id": "analyst_john",
        "requester_role": "REQUESTER",
        "title": "Update KPI-002 Definition",
        "description": "Align formula with regional sales guidelines.",
    }
    res = client.post("/api/v1/approvals", json=payload)
    assert res.status_code == 201
    approval_id = res.json()["approval_id"]

    # Request changes
    changes_payload = {
        "actor_id": "steward_elena",
        "actor_role": "DOMAIN_STEWARD",
        "reason": "Please provide the exact DAX calculation before sign-off.",
    }
    chg_res = client.post(f"/api/v1/approvals/{approval_id}/request-changes", json=changes_payload)
    assert chg_res.status_code == 200
    assert chg_res.json()["status"] == "CHANGES_REQUESTED"

    # Check history endpoint
    hist_res = client.get(f"/api/v1/approvals/{approval_id}/history")
    assert hist_res.status_code == 200
    transitions = hist_res.json()
    assert len(transitions) == 2
    assert transitions[1]["to_state"] == "CHANGES_REQUESTED"


def test_api_list_approvals_and_summary():
    # Queue summary
    sum_res = client.get("/api/v1/approvals/summary")
    assert sum_res.status_code == 200
    data = sum_res.json()
    assert "total_pending" in data
    assert "total_approved" in data

    # List with filtering
    list_res = client.get("/api/v1/approvals?status=APPROVED&limit=10")
    assert list_res.status_code == 200
    assert isinstance(list_res.json(), list)


def test_api_audit_events():
    audit_res = client.get("/api/v1/audit/events?limit=20")
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert isinstance(events, list)
    assert len(events) > 0
    first_event = events[0]
    assert "event_id" in first_event
    assert "actor_id" in first_event
    assert "event_type" in first_event

