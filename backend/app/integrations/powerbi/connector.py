import os
import time
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import httpx
from sqlalchemy.orm import Session

from backend.app.integrations.base import (
    BaseConnector,
    ConnectorStatus,
    ConnectionTestResult,
    ExternalWorkspace,
    ExternalReport,
    ExternalSemanticModel,
    SyncResult,
    IntegrationStatusResponse,
)
from backend.app.models.integrations import IntegrationConfigs, ExternalAssetMappings
from backend.app.models.core import Workspaces, SemanticModels, AnalyticsAssets, Owners

logger = logging.getLogger("bios.integrations.powerbi")


class PowerBiConnector(BaseConnector):
    """
    Production-grade Microsoft Power BI REST API Connector.
    Authenticates via Microsoft Entra ID (Service Principal OAuth2).
    Truthfully reports unconfigured state when credentials are not present.
    """

    REQUIRED_ENV_VARS = [
        "POWERBI_TENANT_ID",
        "POWERBI_CLIENT_ID",
        "POWERBI_CLIENT_SECRET",
    ]

    def __init__(self):
        self._tenant_id = os.getenv("POWERBI_TENANT_ID", "").strip()
        self._client_id = os.getenv("POWERBI_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("POWERBI_CLIENT_SECRET", "").strip()
        self._workspace_filter = os.getenv("POWERBI_WORKSPACE_FILTER", "").strip()
        self._api_base_url = os.getenv("POWERBI_API_URL", "https://api.powerbi.com/v1.0/myorg").strip().rstrip("/")
        
        # Token cache
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def connector_id(self) -> str:
        return "powerbi"

    @property
    def connector_name(self) -> str:
        return "Microsoft Power BI"

    @property
    def platform(self) -> str:
        return "Power BI"

    def is_configured(self) -> bool:
        return bool(self._tenant_id and self._client_id and self._client_secret)

    def _get_token(self) -> str:
        """Acquire or return cached OAuth2 Bearer token from Entra ID."""
        if not self.is_configured():
            raise ValueError("Power BI connector is not configured. Missing Entra ID credentials.")

        now = time.time()
        if self._cached_token and now < (self._token_expires_at - 60):
            return self._cached_token

        token_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "https://analysis.windows.net/powerbi/api/.default",
        }

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(token_url, data=payload)
            if resp.status_code != 200:
                err_detail = resp.text
                logger.error("Entra ID token acquisition failed: HTTP %s", resp.status_code)
                if resp.status_code in (400, 401):
                    raise PermissionError(f"Entra ID authentication failed: Invalid client credentials or tenant ID.")
                raise RuntimeError(f"Entra ID token endpoint error: HTTP {resp.status_code}")

            data = resp.json()
            self._cached_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = now + expires_in
            return self._cached_token

    def _auth_headers(self) -> Dict[str, str]:
        token = self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_connection(self) -> ConnectionTestResult:
        if not self.is_configured():
            return ConnectionTestResult(
                status=ConnectorStatus.NOT_CONFIGURED,
                message="Power BI connector is unconfigured. Set POWERBI_TENANT_ID, POWERBI_CLIENT_ID, and POWERBI_CLIENT_SECRET to enable live synchronization.",
                details={"configured": False, "missing_vars": self._get_missing_vars()},
            )

        start = time.time()
        try:
            headers = self._auth_headers()
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self._api_base_url}/groups?$top=1", headers=headers)
                latency_ms = (time.time() - start) * 1000.0

                if resp.status_code == 200:
                    return ConnectionTestResult(
                        status=ConnectorStatus.CONNECTED,
                        message="Successfully authenticated to Microsoft Power BI REST API.",
                        latency_ms=round(latency_ms, 1),
                        details={"endpoint": self._api_base_url, "tenant_id": self._tenant_id},
                    )
                elif resp.status_code in (401, 403):
                    return ConnectionTestResult(
                        status=ConnectorStatus.PERMISSION_DENIED,
                        message=f"Power BI API permission denied (HTTP {resp.status_code}). Ensure service principal has Tenant.Read.All or Workspace permissions in Power BI Admin Portal.",
                        latency_ms=round(latency_ms, 1),
                    )
                elif resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "60")
                    return ConnectionTestResult(
                        status=ConnectorStatus.SYNC_FAILED,
                        message=f"Power BI API throttled (HTTP 429). Retry after {retry_after}s.",
                        latency_ms=round(latency_ms, 1),
                    )
                else:
                    return ConnectionTestResult(
                        status=ConnectorStatus.AUTH_FAILED,
                        message=f"Unexpected response from Power BI API: HTTP {resp.status_code}",
                        latency_ms=round(latency_ms, 1),
                    )
        except PermissionError as pe:
            return ConnectionTestResult(
                status=ConnectorStatus.AUTH_FAILED,
                message=str(pe),
                latency_ms=round((time.time() - start) * 1000.0, 1),
            )
        except Exception as e:
            return ConnectionTestResult(
                status=ConnectorStatus.AUTH_FAILED,
                message=f"Connection probe failed: {str(e)}",
                latency_ms=round((time.time() - start) * 1000.0, 1),
            )

    def discover_workspaces(self) -> List[ExternalWorkspace]:
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        workspaces: List[ExternalWorkspace] = []
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{self._api_base_url}/groups", headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover workspaces: HTTP %s", resp.status_code)
                return []

            data = resp.json().get("value", [])
            for item in data:
                ws_id = str(item.get("id"))
                ws_name = str(item.get("name", "Unnamed Workspace"))
                if self._workspace_filter and self._workspace_filter.lower() not in ws_name.lower():
                    continue

                workspaces.append(
                    ExternalWorkspace(
                        id=ws_id,
                        name=ws_name,
                        platform=self.platform,
                        description=item.get("description"),
                        capacity_id=item.get("capacityId"),
                    )
                )
        return workspaces

    def discover_reports(self, workspace_id: Optional[str] = None) -> List[ExternalReport]:
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        reports: List[ExternalReport] = []
        with httpx.Client(timeout=15.0) as client:
            url = f"{self._api_base_url}/groups/{workspace_id}/reports" if workspace_id else f"{self._api_base_url}/reports"
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover reports: HTTP %s", resp.status_code)
                return []

            for item in resp.json().get("value", []):
                reports.append(
                    ExternalReport(
                        id=str(item.get("id")),
                        name=str(item.get("name", "Untitled Report")),
                        workspace_id=str(workspace_id or item.get("datasetWorkspaceId", "default")),
                        platform=self.platform,
                        dataset_id=item.get("datasetId"),
                        web_url=item.get("webUrl"),
                        description=item.get("description"),
                    )
                )
        return reports

    def discover_semantic_models(self, workspace_id: Optional[str] = None) -> List[ExternalSemanticModel]:
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        models: List[ExternalSemanticModel] = []
        with httpx.Client(timeout=15.0) as client:
            url = f"{self._api_base_url}/groups/{workspace_id}/datasets" if workspace_id else f"{self._api_base_url}/datasets"
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover datasets: HTTP %s", resp.status_code)
                return []

            for item in resp.json().get("value", []):
                models.append(
                    ExternalSemanticModel(
                        id=str(item.get("id")),
                        name=str(item.get("name", "Untitled Dataset")),
                        workspace_id=str(workspace_id or "default"),
                        platform=self.platform,
                        refresh_status="healthy" if not item.get("isRefreshable") else "healthy",
                        endorsement="promoted" if item.get("isEffectiveIdentityRequired") else "none",
                    )
                )
        return models

    def fetch_asset_metadata(self, external_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None
        headers = self._auth_headers()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self._api_base_url}/reports/{external_id}", headers=headers)
            if resp.status_code == 200:
                return resp.json()
        return None

    def synchronize_assets(self, db: Session, force: bool = False) -> SyncResult:
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)

        # Retrieve or initialize integration config
        config = db.query(IntegrationConfigs).filter(IntegrationConfigs.connector_id == self.connector_id).first()
        if not config:
            config = IntegrationConfigs(
                connector_id=self.connector_id,
                connector_name=self.connector_name,
                status=ConnectorStatus.NOT_CONFIGURED.value,
                auth_type="service_principal",
            )
            db.add(config)
            db.flush()

        if not self.is_configured():
            config.status = ConnectorStatus.NOT_CONFIGURED.value
            config.last_tested_at = now_utc
            config.error_message = "Power BI credentials not configured in environment."
            db.commit()
            return SyncResult(
                connector_id=self.connector_id,
                status=ConnectorStatus.NOT_CONFIGURED.value,
                errors=["Connector unconfigured: Missing POWERBI_TENANT_ID, POWERBI_CLIENT_ID, or POWERBI_CLIENT_SECRET."],
                duration_ms=round((time.time() - start_time) * 1000.0, 1),
            )

        test_res = self.test_connection()
        config.last_tested_at = now_utc
        if test_res.status != ConnectorStatus.CONNECTED:
            config.status = test_res.status.value
            config.error_message = test_res.message
            db.commit()
            return SyncResult(
                connector_id=self.connector_id,
                status=test_res.status.value,
                errors=[test_res.message],
                duration_ms=round((time.time() - start_time) * 1000.0, 1),
            )

        result = SyncResult(connector_id=self.connector_id, status="SUCCESS")

        try:
            # 1. Discover Workspaces
            ext_workspaces = self.discover_workspaces()
            result.imported_workspaces = len(ext_workspaces)

            for ew in ext_workspaces:
                clean_ws_id = f"WS-PBI-{hashlib.md5(ew.id.encode()).hexdigest()[:5].upper()}"
                ws = db.query(Workspaces).filter(Workspaces.workspace_id == clean_ws_id).first()
                if not ws:
                    ws = Workspaces(
                        workspace_id=clean_ws_id,
                        workspace_name=ew.name[:100],
                        scope="Enterprise",
                        environment=ew.environment,
                        platform="Power BI",
                        governance_mode="centralized",
                        classification="internal",
                        synthetic_record=False,
                    )
                    db.add(ws)
                    db.flush()

                # 2. Discover Datasets for workspace
                ext_models = self.discover_semantic_models(ew.id)
                for em in ext_models:
                    clean_model_id = f"SM-PBI-{hashlib.md5(em.id.encode()).hexdigest()[:4].upper()}"
                    model = db.query(SemanticModels).filter(SemanticModels.model_id == clean_model_id).first()
                    if not model:
                        # Find an active owner or fallback
                        owner = db.query(Owners).filter(Owners.status == "active").first()
                        owner_id = owner.owner_id if owner else "OWN-001"

                        model = SemanticModels(
                            model_id=clean_model_id,
                            model_name=em.name[:100],
                            workspace_id=clean_ws_id,
                            product_scope="Enterprise",
                            region_scope="Global",
                            model_type="Power BI semantic model",
                            endorsement=em.endorsement,
                            refresh_frequency="daily",
                            refresh_status=em.refresh_status,
                            owner_id=owner_id,
                            table_count=em.table_count,
                            measure_count=em.measure_count,
                            ai_readiness=em.ai_readiness,
                            ai_issue_pattern="clear",
                            synthetic_record=False,
                        )
                        db.add(model)
                        result.imported_models += 1
                        db.flush()

                # 3. Discover Reports for workspace
                ext_reports = self.discover_reports(ew.id)
                for er in ext_reports:
                    clean_asset_id = f"AST-PBI-{hashlib.md5(er.id.encode()).hexdigest()[:3].upper()}"
                    mapping = (
                        db.query(ExternalAssetMappings)
                        .filter(
                            ExternalAssetMappings.external_platform == self.platform,
                            ExternalAssetMappings.external_id == er.id,
                        )
                        .first()
                    )

                    clean_model_id = f"SM-PBI-{hashlib.md5((er.dataset_id or 'default').encode()).hexdigest()[:4].upper()}"
                    # Verify model exists
                    if not db.query(SemanticModels).filter(SemanticModels.model_id == clean_model_id).first():
                        fallback_model = db.query(SemanticModels).filter(SemanticModels.workspace_id == clean_ws_id).first()
                        clean_model_id = fallback_model.model_id if fallback_model else "SM-001"

                    if not mapping:
                        asset = AnalyticsAssets(
                            asset_id=clean_asset_id,
                            asset_name=er.name[:150],
                            asset_type="Report",
                            platform="Power BI",
                            workspace_id=clean_ws_id,
                            model_id=clean_model_id,
                            product_scope="Enterprise",
                            market_scope="Global",
                            owner_id=None,
                            lifecycle_status="active",
                            endorsement=er.endorsement if er.endorsement in ("certified", "promoted") else "none",
                            estimated_audience=100,
                            classification="internal",
                            delivery_model="central_BI",
                            synthetic_record=False,
                        )
                        db.add(asset)
                        db.flush()

                        mapping = ExternalAssetMappings(
                            external_platform=self.platform,
                            external_id=er.id,
                            internal_asset_id=clean_asset_id,
                            workspace_or_project_id=ew.id,
                            original_name=er.name,
                            source_connector=self.connector_id,
                            last_synced_at=now_utc,
                        )
                        db.add(mapping)
                        result.imported_reports += 1
                    else:
                        # Existing asset: update non-overriding operational metadata
                        asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == mapping.internal_asset_id).first()
                        if asset:
                            asset.last_modified = now_utc
                            mapping.last_synced_at = now_utc
                            result.updated_assets += 1

            # Update configuration status
            config.status = ConnectorStatus.CONNECTED.value
            config.last_synced_at = now_utc
            config.discovered_workspaces = result.imported_workspaces
            config.discovered_reports = result.imported_reports
            config.discovered_models = result.imported_models
            config.error_message = None
            db.commit()

        except Exception as e:
            db.rollback()
            logger.error("Synchronization failed for Power BI: %s", e, exc_info=True)
            result.status = ConnectorStatus.SYNC_FAILED.value
            result.errors.append(str(e))
            config.status = ConnectorStatus.SYNC_FAILED.value
            config.error_message = str(e)
            db.commit()

        result.duration_ms = round((time.time() - start_time) * 1000.0, 1)
        return result

    def _get_missing_vars(self) -> List[str]:
        missing = []
        if not self._tenant_id:
            missing.append("POWERBI_TENANT_ID")
        if not self._client_id:
            missing.append("POWERBI_CLIENT_ID")
        if not self._client_secret:
            missing.append("POWERBI_CLIENT_SECRET")
        return missing

    def get_integration_status(self, db: Optional[Session] = None) -> IntegrationStatusResponse:
        missing = self._get_missing_vars()
        configured = [v for v in self.REQUIRED_ENV_VARS if v not in missing]
        
        status = ConnectorStatus.CONNECTED if self.is_configured() else ConnectorStatus.NOT_CONFIGURED
        last_tested_at = None
        last_synced_at = None
        error_msg = None
        ws_count = 0
        rep_count = 0
        mod_count = 0

        if db:
            cfg = db.query(IntegrationConfigs).filter(IntegrationConfigs.connector_id == self.connector_id).first()
            if cfg:
                status = ConnectorStatus(cfg.status) if cfg.status in ConnectorStatus.__members__ else status
                last_tested_at = cfg.last_tested_at
                last_synced_at = cfg.last_synced_at
                error_msg = cfg.error_message
                ws_count = cfg.discovered_workspaces
                rep_count = cfg.discovered_reports
                mod_count = cfg.discovered_models

        return IntegrationStatusResponse(
            connector_id=self.connector_id,
            connector_name=self.connector_name,
            platform=self.platform,
            status=status,
            auth_type="service_principal",
            last_tested_at=last_tested_at,
            last_synced_at=last_synced_at,
            error_message=error_msg,
            discovered_workspaces=ws_count,
            discovered_reports=rep_count,
            discovered_models=mod_count,
            required_env_vars=self.REQUIRED_ENV_VARS,
            configured_env_vars=configured,
        )

