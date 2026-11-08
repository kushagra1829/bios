import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import Base, engine, SessionLocal
from backend.app.integrations.base import ConnectorStatus
from backend.app.integrations.powerbi.connector import PowerBiConnector
from backend.app.integrations.tableau.connector import TableauConnector
from backend.app.integrations.registry import integration_registry
from backend.app.models.integrations import ExternalAssetMappings, IntegrationConfigs
from backend.app.models.core import AnalyticsAssets, Workspaces, SemanticModels


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        # Clean up any external test records to preserve pristine 360-asset synthetic benchmark baseline
        db.query(ExternalAssetMappings).delete()
        db.query(AnalyticsAssets).filter(AnalyticsAssets.synthetic_record == False).delete()
        db.query(SemanticModels).filter(SemanticModels.synthetic_record == False).delete()
        db.query(Workspaces).filter(Workspaces.synthetic_record == False).delete()
        db.commit()
        db.close()


# -------------------------------------------------------------------------
# Power BI Connector Tests
# -------------------------------------------------------------------------

def test_powerbi_unconfigured_status():
    """Verify Power BI connector returns truthful NOT_CONFIGURED status when env vars missing."""
    with patch.dict("os.environ", {}, clear=True):
        pbi = PowerBiConnector()
        assert not pbi.is_configured()
        res = pbi.test_connection()
        assert res.status == ConnectorStatus.NOT_CONFIGURED
        assert "unconfigured" in res.message.lower()

        status_obj = pbi.get_integration_status()
        assert status_obj.status == ConnectorStatus.NOT_CONFIGURED
        assert "POWERBI_TENANT_ID" in status_obj.required_env_vars


def test_powerbi_auth_failure_handling():
    """Verify connector handles 401 invalid credentials gracefully."""
    mock_env = {
        "POWERBI_TENANT_ID": "test-tenant-123",
        "POWERBI_CLIENT_ID": "test-client-123",
        "POWERBI_CLIENT_SECRET": "bad-secret",
    }
    with patch.dict("os.environ", mock_env, clear=True):
        pbi = PowerBiConnector()
        assert pbi.is_configured()

        with patch.object(pbi, "_get_token", side_effect=PermissionError("Entra ID authentication failed: Invalid client credentials or tenant ID.")):
            res = pbi.test_connection()
            assert res.status == ConnectorStatus.AUTH_FAILED
            assert "authentication failed" in res.message.lower()


def test_powerbi_throttling_handling():
    """Verify connector handles HTTP 429 throttling with Retry-After header."""
    mock_env = {
        "POWERBI_TENANT_ID": "test-tenant-123",
        "POWERBI_CLIENT_ID": "test-client-123",
        "POWERBI_CLIENT_SECRET": "valid-secret",
    }
    with patch.dict("os.environ", mock_env, clear=True):
        pbi = PowerBiConnector()
        pbi._cached_token = "valid-token"
        pbi._token_expires_at = 9999999999

        mock_client = MagicMock()
        mock_resp = MagicMock(status_code=429, headers={"Retry-After": "45"})
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        with patch.object(pbi, "_auth_headers", return_value={"Authorization": "Bearer mock"}):
            with patch("httpx.Client", return_value=mock_client):
                res = pbi.test_connection()
                assert res.status == ConnectorStatus.SYNC_FAILED
                assert "throttled" in res.message.lower()
                assert "45s" in res.message


def test_powerbi_mocked_synchronization(db_session):
    """Verify full ingestion pipeline creates workspaces, models, assets, and mappings idempotently."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    ws_id = f"ws-ext-{uid}"
    ds_id = f"ds-ext-{uid}"
    rep_id = f"rep-ext-{uid}"

    mock_env = {
        "POWERBI_TENANT_ID": "tenant-mock",
        "POWERBI_CLIENT_ID": "client-mock",
        "POWERBI_CLIENT_SECRET": "secret-mock",
    }
    with patch.dict("os.environ", mock_env, clear=True):
        pbi = PowerBiConnector()
        pbi._cached_token = "token-mock"
        pbi._token_expires_at = 9999999999

        with patch.object(pbi, "test_connection", return_value=MagicMock(status=ConnectorStatus.CONNECTED)):
            from backend.app.integrations.base import ExternalWorkspace, ExternalSemanticModel, ExternalReport

            mock_ws = [ExternalWorkspace(id=ws_id, name="Oncology Commercial Hub", platform="Power BI")]
            mock_models = [ExternalSemanticModel(id=ds_id, name="Nubeqa Global Model", workspace_id=ws_id, platform="Power BI")]
            mock_reports = [ExternalReport(id=rep_id, name="Nubeqa Monthly Overview", workspace_id=ws_id, platform="Power BI", dataset_id=ds_id)]

            with patch.object(pbi, "discover_workspaces", return_value=mock_ws), \
                 patch.object(pbi, "discover_semantic_models", return_value=mock_models), \
                 patch.object(pbi, "discover_reports", return_value=mock_reports):

                # First sync
                res1 = pbi.synchronize_assets(db=db_session)
                assert res1.status == "SUCCESS"
                assert res1.imported_workspaces == 1
                assert res1.imported_reports == 1

                # Verify asset exists with synthetic_record == False
                mapping = db_session.query(ExternalAssetMappings).filter(
                    ExternalAssetMappings.external_platform == "Power BI",
                    ExternalAssetMappings.external_id == rep_id,
                ).first()
                assert mapping is not None
                asset = db_session.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == mapping.internal_asset_id).first()
                assert asset is not None
                assert asset.synthetic_record is False
                assert asset.platform == "Power BI"

                # Second sync (idempotent: no duplicate created, updated count increments)
                res2 = pbi.synchronize_assets(db=db_session)
                assert res2.status == "SUCCESS"
                assert res2.imported_reports == 0
                assert res2.updated_assets == 1


# -------------------------------------------------------------------------
# Tableau Connector Tests
# -------------------------------------------------------------------------

def test_tableau_unconfigured_status():
    """Verify Tableau connector returns truthful NOT_CONFIGURED status when PAT is missing."""
    with patch.dict("os.environ", {}, clear=True):
        tab = TableauConnector()
        assert not tab.is_configured()
        res = tab.test_connection()
        assert res.status == ConnectorStatus.NOT_CONFIGURED
        assert "unconfigured" in res.message.lower()

        status_obj = tab.get_integration_status()
        assert status_obj.status == ConnectorStatus.NOT_CONFIGURED
        assert "TABLEAU_SERVER_URL" in status_obj.required_env_vars


def test_tableau_mocked_synchronization(db_session):
    """Verify Tableau synchronization creates external assets and mappings idempotently."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    proj_id = f"proj-ext-{uid}"
    ds_id = f"ds-tab-{uid}"
    wb_id = f"wb-ext-{uid}"

    mock_env = {
        "TABLEAU_SERVER_URL": "https://tableau.mock.example.com",
        "TABLEAU_SITE_NAME": "default",
        "TABLEAU_PAT_NAME": "pat-name",
        "TABLEAU_PAT_SECRET": "pat-secret",
    }
    with patch.dict("os.environ", mock_env, clear=True):
        tab = TableauConnector()
        tab._auth_token = "mock-tableau-token"
        tab._site_id = "site-mock-01"

        with patch.object(tab, "test_connection", return_value=MagicMock(status=ConnectorStatus.CONNECTED)):
            from backend.app.integrations.base import ExternalWorkspace, ExternalSemanticModel, ExternalReport

            mock_ws = [ExternalWorkspace(id=proj_id, name="Cardiology Legacy Analytics", platform="Tableau")]
            mock_models = [ExternalSemanticModel(id=ds_id, name="Kerendia Regional Extract", workspace_id=proj_id, platform="Tableau")]
            mock_reports = [ExternalReport(id=wb_id, name="Kerendia Regional Report", workspace_id=proj_id, platform="Tableau")]

            with patch.object(tab, "discover_workspaces", return_value=mock_ws), \
                 patch.object(tab, "discover_semantic_models", return_value=mock_models), \
                 patch.object(tab, "discover_reports", return_value=mock_reports):

                res = tab.synchronize_assets(db=db_session)
                assert res.status == "SUCCESS"
                assert res.imported_workspaces == 1
                assert res.imported_reports == 1

                # Verify mapping exists
                mapping = db_session.query(ExternalAssetMappings).filter(
                    ExternalAssetMappings.external_platform == "Tableau",
                    ExternalAssetMappings.external_id == wb_id,
                ).first()
                assert mapping is not None
                asset = db_session.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == mapping.internal_asset_id).first()
                assert asset is not None
                assert asset.synthetic_record is False
                assert asset.platform == "Tableau"


# -------------------------------------------------------------------------
# Integration REST API Tests
# -------------------------------------------------------------------------

ADMIN_HEADERS = {"X-Actor-Id": "ADM-001", "X-Actor-Role": "BIOS_ADMIN"}


def test_api_list_integrations(client):
    """Verify GET /api/v1/integrations returns statuses for Power BI and Tableau."""
    resp = client.get("/api/v1/integrations", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    connector_ids = [d["connector_id"] for d in data]
    assert "powerbi" in connector_ids
    assert "tableau" in connector_ids


def test_api_test_integration_endpoint(client):
    """Verify POST /api/v1/integrations/{id}/test probes connection."""
    resp = client.post("/api/v1/integrations/powerbi/test", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "message" in data


def test_api_unknown_connector_404(client):
    """Verify 404 for nonexistent connector."""
    resp = client.get("/api/v1/integrations/unknown_tool", headers=ADMIN_HEADERS)
    assert resp.status_code == 404
