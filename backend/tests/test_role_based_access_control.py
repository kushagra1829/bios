"""
BIOS 1.0 Enterprise Role-Based Access Control (RBAC) & Scoping Test Suite.
Validates workspace barriers, query-level scoping, approval hierarchy, and anti-escalation controls.
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.models.approval import ApprovalRequests


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


# =========================================================================
# 1. DIRECT API ACCESS & PRIVILEGE BARRIERS (403 FORBIDDEN)
# =========================================================================

def test_requester_restricted_api_barriers(client):
    """
    Verify that REQUESTER / ANALYST role is strictly forbidden (HTTP 403) from accessing
    governance evaluations, findings, alerts, lifecycle actions, artifacts, monitoring, and admin APIs.
    """
    headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}

    # Integrations & Ingestion (Admin only)
    assert client.get("/api/v1/integrations", headers=headers).status_code == 403
    assert client.post("/api/v1/integrations/powerbi/test", headers=headers).status_code == 403
    assert client.post("/api/v1/ingestion/run", headers=headers).status_code == 403

    # Continuous Monitoring (Governance Reviewer & Admin only)
    assert client.get("/api/v1/monitoring/summary", headers=headers).status_code == 403
    assert client.get("/api/v1/monitoring/jobs", headers=headers).status_code == 403
    assert client.post("/api/v1/monitoring/jobs/run", json={"job_type": "FULL_CONTINUOUS_SCAN"}, headers=headers).status_code == 403

    # Development Studio Artifacts (Steward, Reviewer, Admin only)
    assert client.get("/api/v1/artifacts", headers=headers).status_code == 403
    assert client.post("/api/v1/artifacts/specifications", json={"title": "Test", "business_purpose": "Test"}, headers=headers).status_code == 403

    # Governance Evaluation & Findings (Owners, Stewards, Reviewers only)
    assert client.post("/api/v1/governance/evaluate", headers=headers).status_code == 403
    assert client.get("/api/v1/governance/findings", headers=headers).status_code == 403

    # Alert Centre (Owners, Stewards, Reviewers only)
    assert client.get("/api/v1/alerts", headers=headers).status_code == 403

    # Lifecycle Evaluations (Owners, Stewards, Reviewers only)
    assert client.post("/api/v1/lifecycle/evaluate", headers=headers).status_code == 403


def test_asset_owner_restricted_api_barriers(client):
    """
    Verify that ASSET_OWNER role is restricted from platform admin, continuous monitoring,
    artifact studio, and full governance re-evaluation.
    """
    headers = {"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"}

    # Blocked on Admin & Monitoring
    assert client.get("/api/v1/integrations", headers=headers).status_code == 403
    assert client.post("/api/v1/ingestion/run", headers=headers).status_code == 403
    assert client.get("/api/v1/monitoring/summary", headers=headers).status_code == 403
    assert client.get("/api/v1/artifacts", headers=headers).status_code == 403
    assert client.post("/api/v1/governance/evaluate", headers=headers).status_code == 403

    # Permitted on Alerts, Findings, Lifecycle, and Approvals
    assert client.get("/api/v1/alerts", headers=headers).status_code == 200
    assert client.get("/api/v1/governance/findings", headers=headers).status_code == 200
    assert client.get("/api/v1/approvals", headers=headers).status_code == 200


def test_domain_steward_restricted_api_barriers(client):
    """
    Verify that DOMAIN_STEWARD role is restricted from platform admin and continuous monitoring,
    but permitted on Development Studio artifacts, Governance, Alerts, and Lifecycle.
    """
    headers = {"X-Actor-Id": "OWN-003", "X-Actor-Role": "DOMAIN_STEWARD"}

    # Blocked on Admin & Monitoring
    assert client.get("/api/v1/integrations", headers=headers).status_code == 403
    assert client.get("/api/v1/monitoring/summary", headers=headers).status_code == 403

    # Permitted on Artifacts, Alerts, Findings, Lifecycle, Approvals
    assert client.get("/api/v1/artifacts", headers=headers).status_code == 200
    assert client.get("/api/v1/alerts", headers=headers).status_code == 200
    assert client.get("/api/v1/governance/findings", headers=headers).status_code == 200
    assert client.get("/api/v1/approvals", headers=headers).status_code == 200


def test_governance_reviewer_restricted_from_admin(client):
    """
    Verify that BI_GOVERNANCE_REVIEWER is restricted from Platform Administration & Integrations,
    preserving separation between governance oversight and infrastructure credentials.
    """
    headers = {"X-Actor-Id": "REV-001", "X-Actor-Role": "BI_GOVERNANCE_REVIEWER"}

    assert client.get("/api/v1/integrations", headers=headers).status_code == 403
    assert client.post("/api/v1/ingestion/run", headers=headers).status_code == 403

    # Permitted on Continuous Monitoring, Governance, Alerts, Lifecycle, Artifacts
    assert client.get("/api/v1/monitoring/summary", headers=headers).status_code == 200
    assert client.get("/api/v1/governance/findings", headers=headers).status_code == 200
    assert client.get("/api/v1/artifacts", headers=headers).status_code == 200


def test_bios_admin_full_access(client):
    """
    Verify that BIOS_ADMIN possesses administrative authority across all endpoints.
    """
    headers = {"X-Actor-Id": "ADMIN-001", "X-Actor-Role": "BIOS_ADMIN"}

    assert client.get("/api/v1/integrations", headers=headers).status_code == 200
    assert client.get("/api/v1/monitoring/summary", headers=headers).status_code == 200
    assert client.get("/api/v1/artifacts", headers=headers).status_code == 200
    assert client.get("/api/v1/alerts", headers=headers).status_code == 200


# =========================================================================
# 2. DATA SCOPING & ISOLATION AT QUERY LEVEL
# =========================================================================

def test_requester_approval_data_isolation(client, db):
    """
    Verify that a Requester can ONLY see their own submitted approval requests,
    and cannot discover other users' requests.
    """
    headers = {"X-Actor-Id": "ISOLATED-REQ-999", "X-Actor-Role": "REQUESTER"}
    resp = client.get("/api/v1/approvals", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 0, "New requester must not see any existing private approvals"


def test_requester_cannot_access_foreign_approval_detail(client, db):
    """
    Verify that a Requester attempting to view the detail of another user's approval request
    is rejected with HTTP 403 Forbidden.
    """
    admin_headers = {"X-Actor-Role": "BIOS_ADMIN"}
    approvals = client.get("/api/v1/approvals", headers=admin_headers).json()
    assert len(approvals) > 0
    foreign_approval = approvals[0]

    # Requester with different ID
    req_headers = {"X-Actor-Id": "DIFFERENT-USER-123", "X-Actor-Role": "REQUESTER"}
    detail_resp = client.get(f"/api/v1/approvals/{foreign_approval['approval_id']}", headers=req_headers)
    assert detail_resp.status_code == 403
    assert "private" in detail_resp.json()["error"].lower() or "denied" in detail_resp.json()["error"].lower()


def test_asset_owner_approval_scoping(client, db):
    """
    Verify that an Asset Owner (e.g. OWN-001) only sees approvals targeting assets they own.
    """
    headers = {"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"}
    resp = client.get("/api/v1/approvals", headers=headers)
    assert resp.status_code == 200
    owned_asset_ids = set(a[0] for a in db.query(AnalyticsAssets.asset_id).filter(AnalyticsAssets.owner_id == "OWN-001").all())
    for item in resp.json():
        if item.get("target_entity_type") == "asset":
            assert item.get("target_entity_id") in owned_asset_ids, f"Leaked approval for non-owned asset {item.get('target_entity_id')}"


# =========================================================================
# 3. APPROVAL AUTHORITY & ANTI-SELF-APPROVAL SAFEGUARDS
# =========================================================================

def test_requester_cannot_adjudicate_approvals(client):
    """
    Verify that Requesters/Analysts cannot approve or reject any approval request.
    """
    headers = {"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"}
    admin_headers = {"X-Actor-Role": "BIOS_ADMIN"}
    app_id = client.get("/api/v1/approvals", headers=admin_headers).json()[0]["approval_id"]

    approve_resp = client.post(
        f"/api/v1/approvals/{app_id}/approve",
        json={"actor_id": "REQ-001", "actor_role": "REQUESTER", "reason": "Self authorizing action"},
        headers=headers,
    )
    assert approve_resp.status_code == 403

    reject_resp = client.post(
        f"/api/v1/approvals/{app_id}/reject",
        json={"actor_id": "REQ-001", "actor_role": "REQUESTER", "reason": "Self rejecting action"},
        headers=headers,
    )
    assert reject_resp.status_code == 403


# =========================================================================
# 4. ROLE-SCOPED DASHBOARD TELEMETRY
# =========================================================================

def test_dashboard_telemetry_all_four_roles(client):
    """
    Verify that /api/v1/dashboard/telemetry delivers customized, role-tailored payloads
    for Requester, Asset Owner, Domain Steward, and BI Governance Reviewer.
    """
    # 1. Requester
    r_res = client.get("/api/v1/dashboard/telemetry", headers={"X-Actor-Id": "REQ-001", "X-Actor-Role": "REQUESTER"})
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert r_data["role"] == "REQUESTER"
    assert "my_requests_count" in r_data
    assert "trusted_assets_count" in r_data

    # 2. Asset Owner
    ao_res = client.get("/api/v1/dashboard/telemetry", headers={"X-Actor-Id": "OWN-001", "X-Actor-Role": "ASSET_OWNER"})
    assert ao_res.status_code == 200
    ao_data = ao_res.json()
    assert ao_data["role"] == "ASSET_OWNER"
    assert "assigned_assets_count" in ao_data
    assert "endorsement_breakdown" in ao_data
    assert "active_findings_count" in ao_data

    # 3. Domain Steward
    ds_res = client.get("/api/v1/dashboard/telemetry", headers={"X-Actor-Id": "OWN-003", "X-Actor-Role": "DOMAIN_STEWARD"})
    assert ds_res.status_code == 200
    ds_data = ds_res.json()
    assert ds_data["role"] == "DOMAIN_STEWARD"
    assert "domain_assets_count" in ds_data
    assert "ai_ready_models_count" in ds_data
    assert "canonical_kpis_count" in ds_data

    # 4. BI Governance Reviewer
    gov_res = client.get("/api/v1/dashboard/telemetry", headers={"X-Actor-Id": "REV-001", "X-Actor-Role": "BI_GOVERNANCE_REVIEWER"})
    assert gov_res.status_code == 200
    gov_data = gov_res.json()
    assert gov_data["role"] == "BI_GOVERNANCE_REVIEWER"
    assert gov_data["total_assets"] == 360
    assert gov_data["certified_assets"] == 50
    assert "findings_by_severity" in gov_data
