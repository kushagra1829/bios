from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_list_assets():
    response = client.get("/api/v1/assets?page=1&page_size=20")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "meta" in data
    assert data["meta"]["total"] == 360
    assert len(data["items"]) == 20


def test_filter_unowned_assets():
    response = client.get("/api/v1/assets?unowned_only=true")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 21
    for item in data["items"]:
        assert item["owner_id"] is None


def test_get_asset_detail_and_404():
    response = client.get("/api/v1/assets/AST-0001")
    assert response.status_code == 200
    asset = response.json()
    assert asset["asset_id"] == "AST-0001"
    assert asset["workspace"] is not None
    assert asset["semantic_model"] is not None

    not_found = client.get("/api/v1/assets/AST-999999")
    assert not_found.status_code == 404
    assert "not found" in not_found.json()["error"].lower()


def test_list_workspaces():
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 16


def test_list_owners():
    response = client.get("/api/v1/owners")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 60


def test_list_semantic_models():
    response = client.get("/api/v1/semantic-models")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 75


def test_list_kpis():
    response = client.get("/api/v1/kpis")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 56


def test_list_asset_usage():
    response = client.get("/api/v1/asset-usage?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 3600
    assert len(data["items"]) == 10


def test_list_lineage():
    response = client.get("/api/v1/lineage")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 438


def test_list_governance_signals():
    response = client.get("/api/v1/governance-signals")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 410


def test_list_migration_backlog():
    response = client.get("/api/v1/migration-backlog")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 94


def test_ingestion_status():
    response = client.get("/api/v1/ingestion/status")
    assert response.status_code == 200
    data = response.json()
    assert "import_id" in data
    assert data["status"] == "success"
    assert data["total_records_processed"] in (8100, 8148)

