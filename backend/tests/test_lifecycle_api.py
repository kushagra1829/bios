from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_post_lifecycle_evaluate():
    response = client.post("/api/v1/lifecycle/evaluate")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["total_assessed"] == 360
    assert "lifecycle_breakdown" in data
    assert "migration_breakdown" in data
    assert data["execution_time_ms"] > 0


def test_get_lifecycle_summary():
    response = client.get("/api/v1/lifecycle/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["total_assets_assessed"] == 360
    assert "actions_breakdown" in data
    assert data["avg_composite_score"] > 0
    assert data["assets_blocked_by_dependencies"] > 0
    assert data["rationalization_opportunities"] > 0


def test_list_lifecycle_recommendations_and_filter():
    response = client.get("/api/v1/lifecycle/recommendations?limit=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 20

    # Filter by action CONSOLIDATE
    res_cons = client.get("/api/v1/lifecycle/recommendations?action=CONSOLIDATE&limit=10")
    assert res_cons.status_code == 200
    cons_data = res_cons.json()
    assert len(cons_data) > 0
    for item in cons_data:
        assert item["recommended_action"] == "CONSOLIDATE"


def test_get_single_lifecycle_recommendation():
    # Fetch first valid recommendation
    list_res = client.get("/api/v1/lifecycle/recommendations?limit=1")
    assert list_res.status_code == 200
    rec = list_res.json()[0]

    # Query by assessment_id
    res_by_id = client.get(f"/api/v1/lifecycle/recommendations/{rec['assessment_id']}")
    assert res_by_id.status_code == 200
    assert res_by_id.json()["assessment_id"] == rec["assessment_id"]

    # Query by asset_id
    res_by_asset = client.get(f"/api/v1/lifecycle/recommendations/{rec['asset_id']}")
    assert res_by_asset.status_code == 200
    assert res_by_asset.json()["asset_id"] == rec["asset_id"]

    # 404 handler
    bad_res = client.get("/api/v1/lifecycle/recommendations/NON_EXISTENT_ASM")
    assert bad_res.status_code == 404


def test_get_migration_summary():
    response = client.get("/api/v1/migration/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["total_tableau_assets"] == 94
    assert "actions_breakdown" in data
    assert "complexity_breakdown" in data
    assert data["estimated_effort_reduction_pct"] > 30.0


def test_list_migration_recommendations_and_filter():
    response = client.get("/api/v1/migration/recommendations?limit=20")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 20

    # Filter by complexity 'high'
    res_high = client.get("/api/v1/migration/recommendations?complexity=high&limit=10")
    assert res_high.status_code == 200
    high_data = res_high.json()
    assert len(high_data) > 0
    for item in high_data:
        assert item["technical_complexity"] == "high"

