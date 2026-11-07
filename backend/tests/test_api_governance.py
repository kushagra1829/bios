from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_get_governance_rules():
    response = client.get("/api/v1/governance/rules")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    rule_ids = [r["rule_id"] for r in data]
    assert "RULE-001" in rule_ids
    assert "RULE-008" in rule_ids


def test_get_single_governance_rule():
    response = client.get("/api/v1/governance/rules/RULE-001")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "RULE-001"
    assert data["rule_name"] == "Reuse before build"

    # Non-existent rule returns 404
    bad_res = client.get("/api/v1/governance/rules/RULE-999")
    assert bad_res.status_code == 404


def test_trigger_evaluation_endpoint():
    response = client.post("/api/v1/governance/evaluate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_findings"] > 0
    assert "findings_by_severity" in data
    assert "findings_by_rule" in data


def test_get_governance_summary():
    response = client.get("/api/v1/governance/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_active_findings" in data
    assert "findings_by_severity" in data
    assert data["total_active_findings"] > 0


def test_list_findings_pagination_and_filtering():
    # Base listing with limit
    response = client.get("/api/v1/governance/findings?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 10

    # Filter by rule_id
    res_rule = client.get("/api/v1/governance/findings?rule_id=RULE-003&limit=50")
    assert res_rule.status_code == 200
    rule_data = res_rule.json()
    assert len(rule_data) > 0
    for item in rule_data:
        assert item["rule_id"] == "RULE-003"

    # Filter by severity
    res_crit = client.get("/api/v1/governance/findings?severity=critical&limit=50")
    assert res_crit.status_code == 200
    crit_data = res_crit.json()
    assert len(crit_data) > 0
    for item in crit_data:
        assert item["severity"] == "critical"


def test_get_single_finding_and_404():
    # Get any valid finding
    list_res = client.get("/api/v1/governance/findings?limit=1")
    assert list_res.status_code == 200
    findings = list_res.json()
    assert len(findings) == 1
    finding_id = findings[0]["finding_id"]

    # Fetch specific
    res = client.get(f"/api/v1/governance/findings/{finding_id}")
    assert res.status_code == 200
    assert res.json()["finding_id"] == finding_id

    # Non-existent
    bad_res = client.get("/api/v1/governance/findings/FND-INVALID-999")
    assert bad_res.status_code == 404

