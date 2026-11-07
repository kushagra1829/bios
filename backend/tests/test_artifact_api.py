import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.models.approval import ApprovalRequests
from backend.app.models.assistant import AssistantRecommendations, AssistantRequests

client = TestClient(app)


def test_api_specifications_crud():
    # 1. Create specification
    payload = {
        "title": "Oncology Portfolio Performance",
        "business_purpose": "Track Oncology net sales and volume trends",
        "product_scope": "ONCOLOGY",
        "market_scope": "GLOBAL",
        "kpi_ids": ["KPI-001", "KPI-004", "KPI-027"],
    }
    res = client.post("/api/v1/artifacts/specifications", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["spec_id"].startswith("SPEC-")
    assert data["title"] == "Oncology Portfolio Performance"
    spec_id = data["spec_id"]

    # 2. Get specification
    res2 = client.get(f"/api/v1/artifacts/specifications/{spec_id}")
    assert res2.status_code == 200
    assert res2.json()["spec_id"] == spec_id


def test_api_generate_and_validation():
    # Create a spec first
    spec_payload = {
        "title": "API Generated Dashboard",
        "business_purpose": "Testing generation via REST API",
        "product_scope": "GLOBAL",
        "market_scope": "GLOBAL",
    }
    res_spec = client.post("/api/v1/artifacts/specifications", json=spec_payload)
    assert res_spec.status_code == 201
    spec_id = res_spec.json()["spec_id"]

    # Generate artifact with force=True
    gen_payload = {
        "spec_id": spec_id,
        "actor_id": "API_TESTER",
        "force": True,
    }
    res_gen = client.post("/api/v1/artifacts/generate", json=gen_payload)
    assert res_gen.status_code == 201, res_gen.text
    art_data = res_gen.json()
    art_id = art_data["artifact_id"]
    assert art_id.startswith("ART-")
    assert art_data["status"] in ("validated", "generated")

    # List artifacts
    res_list = client.get("/api/v1/artifacts")
    assert res_list.status_code == 200
    ids = [a["artifact_id"] for a in res_list.json()]
    assert art_id in ids

    # Get artifact by ID
    res_get = client.get(f"/api/v1/artifacts/{art_id}")
    assert res_get.status_code == 200
    assert res_get.json()["artifact_id"] == art_id

    # Validate endpoint
    res_val = client.post(f"/api/v1/artifacts/{art_id}/validate")
    assert res_val.status_code == 200
    val_data = res_val.json()
    assert val_data["overall_status"] in ("VALID", "VALID_WITH_UNVERIFIED_DESKTOP")

    # Get validation report
    res_rep = client.get(f"/api/v1/artifacts/{art_id}/validation")
    assert res_rep.status_code == 200
    assert res_rep.json()["overall_status"] in ("VALID", "VALID_WITH_UNVERIFIED_DESKTOP")


def test_api_reuse_gate_rejection():
    db = SessionLocal()
    req_id = f"REQ-API-CONSOLIDATE-{uuid.uuid4().hex[:6]}"
    try:
        assistant_req = AssistantRequests(
            request_id=req_id,
            raw_prompt="New Nubeqa sales dashboard",
            status="completed",
        )
        rec = AssistantRecommendations(
            recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
            request_id=req_id,
            decision="CONSOLIDATE",
            confidence=0.91,
            primary_recommendation="Consolidate with AST-0065",
            rationale="Duplicate asset detected",
        )
        db.add(assistant_req)
        db.add(rec)
        db.commit()
    finally:
        db.close()

    # Generate request linking this request_id without force
    gen_payload = {
        "request_id": req_id,
        "actor_id": "BUSINESS_USER",
        "force": False,
    }
    res = client.post("/api/v1/artifacts/generate", json=gen_payload)
    assert res.status_code == 409
    err = res.json()
    assert err["error"]["error"] == "REUSE_GATE_VETO"
    assert "CONSOLIDATE" in err["error"]["message"]


def test_api_build_new_approval_gate():
    db = SessionLocal()
    req_id = f"REQ-API-BUILDNEW-{uuid.uuid4().hex[:6]}"
    try:
        assistant_req = AssistantRequests(
            request_id=req_id,
            raw_prompt="Build new Kerendia China dashboard",
            status="completed",
        )
        rec = AssistantRecommendations(
            recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
            request_id=req_id,
            decision="BUILD_NEW",
            confidence=0.94,
            primary_recommendation="Build new dashboard",
            rationale="Novel scope",
        )
        db.add(assistant_req)
        db.add(rec)
        db.commit()
    finally:
        db.close()

    # Attempt without approval -> 403 Forbidden
    gen_payload = {
        "request_id": req_id,
        "actor_id": "BUSINESS_USER",
        "force": False,
    }
    res = client.post("/api/v1/artifacts/generate", json=gen_payload)
    assert res.status_code == 403
    err = res.json()
    assert err["error"]["error"] == "APPROVAL_REQUIRED"
