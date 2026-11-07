from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_api_submit_assistant_request():
    payload = {
        "prompt": "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."
    }
    response = client.post("/api/v1/assistant/requests", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "request_id" in data
    assert data["status"] == "completed"
    assert "intent" in data
    assert "recommendation" in data
    assert "traces" in data
    assert len(data["traces"]) == 6

    req_id = data["request_id"]

    # Test GET /api/v1/assistant/requests/{request_id}
    res_get = client.get(f"/api/v1/assistant/requests/{req_id}")
    assert res_get.status_code == 200
    assert res_get.json()["request_id"] == req_id

    # Test GET /api/v1/assistant/requests/{request_id}/recommendation
    res_rec = client.get(f"/api/v1/assistant/requests/{req_id}/recommendation")
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert rec_data["request_id"] == req_id
    assert "decision" in rec_data

    # Test GET /api/v1/assistant/requests/{request_id}/trace
    res_trc = client.get(f"/api/v1/assistant/requests/{req_id}/trace")
    assert res_trc.status_code == 200
    traces = res_trc.json()
    assert len(traces) == 6
    assert traces[0]["agent_name"] == "IntentAgent"
    assert traces[5]["agent_name"] == "DecisionAgent"


def test_api_list_requests():
    response = client.get("/api/v1/assistant/requests?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_request_404_handlers():
    res_req = client.get("/api/v1/assistant/requests/REQ-INVALID-999")
    assert res_req.status_code == 404

    res_rec = client.get("/api/v1/assistant/requests/REQ-INVALID-999/recommendation")
    assert res_rec.status_code == 404

    res_trc = client.get("/api/v1/assistant/requests/REQ-INVALID-999/trace")
    assert res_trc.status_code == 404

