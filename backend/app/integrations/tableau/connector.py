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

logger = logging.getLogger("bios.integrations.tableau")


class TableauConnector(BaseConnector):
    """
    Production-grade Tableau Server / Cloud REST API Connector.
    Authenticates via Personal Access Token (PAT) or Basic Credentials.
    Truthfully reports unconfigured state when credentials are not present.
    """

    REQUIRED_ENV_VARS = [
        "TABLEAU_SERVER_URL",
        "TABLEAU_SITE_NAME",
        "TABLEAU_PAT_NAME",
        "TABLEAU_PAT_SECRET",
    ]

    def __init__(self):
        self._server_url = os.getenv("TABLEAU_SERVER_URL", "").strip().rstrip("/")
        self._site_name = os.getenv("TABLEAU_SITE_NAME", "").strip()
        self._pat_name = os.getenv("TABLEAU_PAT_NAME", "").strip()
        self._pat_secret = os.getenv("TABLEAU_PAT_SECRET", "").strip()
        self._api_version = os.getenv("TABLEAU_API_VERSION", "3.22").strip()

        # Session token cache
        self._auth_token: Optional[str] = None
        self._site_id: Optional[str] = None
        self._user_id: Optional[str] = None

    @property
    def connector_id(self) -> str:
        return "tableau"

    @property
    def connector_name(self) -> str:
        return "Tableau Server / Cloud"

    @property
    def platform(self) -> str:
        return "Tableau"

    def is_configured(self) -> bool:
        return bool(self._server_url and self._pat_name and self._pat_secret)

    def _sign_in(self) -> str:
        """Authenticate to Tableau REST API and obtain session token."""
        if not self.is_configured():
            raise ValueError("Tableau connector is not configured. Missing TABLEAU_SERVER_URL, TABLEAU_PAT_NAME, or TABLEAU_PAT_SECRET.")

        if self._auth_token and self._site_id:
            return self._auth_token

        sign_in_url = f"{self._server_url}/api/{self._api_version}/auth/signin"
        payload = {
            "credentials": {
                "personalAccessTokenName": self._pat_name,
                "personalAccessTokenSecret": self._pat_secret,
                "site": {"contentUrl": self._site_name},
            }
        }

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(sign_in_url, json=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
            if resp.status_code != 200:
                logger.error("Tableau sign-in failed: HTTP %s", resp.status_code)
                if resp.status_code in (401, 403):
                    raise PermissionError(f"Tableau authentication failed: Invalid Personal Access Token or Site '{self._site_name}'.")
                raise RuntimeError(f"Tableau REST API error: HTTP {resp.status_code}")

            data = resp.json()
            creds = data.get("credentials", {})
            self._auth_token = creds.get("token")
            self._site_id = creds.get("site", {}).get("id")
            self._user_id = creds.get("user", {}).get("id")
            return self._auth_token

    def _auth_headers(self) -> Dict[str, str]:
        token = self._sign_in()
        return {
            "X-Tableau-Auth": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_connection(self) -> ConnectionTestResult:
        if not self.is_configured():
            return ConnectionTestResult(
                status=ConnectorStatus.NOT_CONFIGURED,
                message="Tableau connector is unconfigured. Set TABLEAU_SERVER_URL, TABLEAU_SITE_NAME, TABLEAU_PAT_NAME, and TABLEAU_PAT_SECRET to enable live synchronization.",
                details={"configured": False, "missing_vars": self._get_missing_vars()},
            )

        start = time.time()
        try:
            self._sign_in()
            latency_ms = (time.time() - start) * 1000.0
            return ConnectionTestResult(
                status=ConnectorStatus.CONNECTED,
                message="Successfully authenticated to Tableau REST API.",
                latency_ms=round(latency_ms, 1),
                details={"server_url": self._server_url, "site_id": self._site_id},
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
                message=f"Tableau probe failed: {str(e)}",
                latency_ms=round((time.time() - start) * 1000.0, 1),
            )

    def discover_workspaces(self) -> List[ExternalWorkspace]:
        """Discover Tableau Projects (treated as workspaces in BIOS)."""
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        projects: List[ExternalWorkspace] = []
        with httpx.Client(timeout=15.0) as client:
            url = f"{self._server_url}/api/{self._api_version}/sites/{self._site_id}/projects"
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover Tableau projects: HTTP %s", resp.status_code)
                return []

            data = resp.json().get("projects", {}).get("project", [])
            if isinstance(data, dict):
                data = [data]
            for proj in data:
                projects.append(
                    ExternalWorkspace(
                        id=str(proj.get("id")),
                        name=str(proj.get("name", "Default Project")),
                        platform=self.platform,
                        description=proj.get("description"),
                        environment="Production",
                    )
                )
        return projects

    def discover_reports(self, workspace_id: Optional[str] = None) -> List[ExternalReport]:
        """Discover Tableau Workbooks (treated as reports/assets in BIOS)."""
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        workbooks: List[ExternalReport] = []
        with httpx.Client(timeout=15.0) as client:
            url = f"{self._server_url}/api/{self._api_version}/sites/{self._site_id}/workbooks"
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover Tableau workbooks: HTTP %s", resp.status_code)
                return []

            data = resp.json().get("workbooks", {}).get("workbook", [])
            if isinstance(data, dict):
                data = [data]
            for wb in data:
                proj_id = wb.get("project", {}).get("id", "default")
                if workspace_id and proj_id != workspace_id:
                    continue

                workbooks.append(
                    ExternalReport(
                        id=str(wb.get("id")),
                        name=str(wb.get("name", "Untitled Workbook")),
                        workspace_id=str(proj_id),
                        platform=self.platform,
                        web_url=wb.get("webpageUrl"),
                        description=wb.get("description"),
                    )
                )
        return workbooks

    def discover_semantic_models(self, workspace_id: Optional[str] = None) -> List[ExternalSemanticModel]:
        """Discover Tableau Published Data Sources."""
        if not self.is_configured():
            return []

        headers = self._auth_headers()
        datasources: List[ExternalSemanticModel] = []
        with httpx.Client(timeout=15.0) as client:
            url = f"{self._server_url}/api/{self._api_version}/sites/{self._site_id}/datasources"
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("Failed to discover Tableau datasources: HTTP %s", resp.status_code)
                return []

            data = resp.json().get("datasources", {}).get("datasource", [])
            if isinstance(data, dict):
                data = [data]
            for ds in data:
                proj_id = ds.get("project", {}).get("id", "default")
                if workspace_id and proj_id != workspace_id:
                    continue

                datasources.append(
                    ExternalSemanticModel(
                        id=str(ds.get("id")),
                        name=str(ds.get("name", "Untitled Datasource")),
                        workspace_id=str(proj_id),
                        platform=self.platform,
                        refresh_status="healthy",
                        endorsement="certified" if ds.get("isCertified") else "none",
                        table_count=1,
                        measure_count=1,
                        ai_readiness="partial",
                    )
                )
        return datasources

    def fetch_asset_metadata(self, external_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None
        headers = self._auth_headers()
        with httpx.Client(timeout=10.0) as client:
            url = f"{self._server_url}/api/{self._api_version}/sites/{self._site_id}/workbooks/{external_id}"
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
        return None

    def synchronize_assets(self, db: Session, force: bool = False) -> SyncResult:
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)

        config = db.query(IntegrationConfigs).filter(IntegrationConfigs.connector_id == self.connector_id).first()
        if not config:
            config = IntegrationConfigs(
                connector_id=self.connector_id,
                connector_name=self.connector_name,
                status=ConnectorStatus.NOT_CONFIGURED.value,
                auth_type="pat",
            )
            db.add(config)
            db.flush()

        if not self.is_configured():
            config.status = ConnectorStatus.NOT_CONFIGURED.value
            config.last_tested_at = now_utc
            config.error_message = "Tableau credentials not configured in environment."
            db.commit()
            return SyncResult(
                connector_id=self.connector_id,
                status=ConnectorStatus.NOT_CONFIGURED.value,
                errors=["Connector unconfigured: Missing TABLEAU_SERVER_URL, TABLEAU_PAT_NAME, or TABLEAU_PAT_SECRET."],
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
            # 1. Discover Projects as Workspaces
            ext_projects = self.discover_workspaces()
            result.imported_workspaces = len(ext_projects)

            for ep in ext_projects:
                clean_ws_id = f"WS-TAB-{hashlib.md5(ep.id.encode()).hexdigest()[:5].upper()}"
                ws = db.query(Workspaces).filter(Workspaces.workspace_id == clean_ws_id).first()
                if not ws:
                    ws = Workspaces(
                        workspace_id=clean_ws_id,
                        workspace_name=ep.name[:100],
                        scope="Enterprise",
                        environment="Production",
                        platform="Tableau",
                        governance_mode="distributed",
                        classification="internal",
                        synthetic_record=False,
                    )
                    db.add(ws)
                    db.flush()

                # 2. Discover Datasources as Models
                ext_models = self.discover_semantic_models(ep.id)
                for em in ext_models:
                    clean_model_id = f"SM-TAB-{hashlib.md5(em.id.encode()).hexdigest()[:4].upper()}"
                    model = db.query(SemanticModels).filter(SemanticModels.model_id == clean_model_id).first()
                    if not model:
                        owner = db.query(Owners).filter(Owners.status == "active").first()
                        owner_id = owner.owner_id if owner else "OWN-001"

                        model = SemanticModels(
                            model_id=clean_model_id,
                            model_name=em.name[:100],
                            workspace_id=clean_ws_id,
                            product_scope="Enterprise",
                            region_scope="Global",
                            model_type="Tableau published datasource",
                            endorsement=em.endorsement,
                            refresh_frequency="daily",
                            refresh_status="healthy",
                            owner_id=owner_id,
                            table_count=em.table_count,
                            measure_count=em.measure_count,
                            ai_readiness="partial",
                            ai_issue_pattern="clear",
                            synthetic_record=False,
                        )
                        db.add(model)
                        result.imported_models += 1
                        db.flush()

                # 3. Discover Workbooks as Assets
                ext_workbooks = self.discover_reports(ep.id)
                for ew in ext_workbooks:
                    clean_asset_id = f"AST-TAB-{hashlib.md5(ew.id.encode()).hexdigest()[:3].upper()}"
                    mapping = (
                        db.query(ExternalAssetMappings)
                        .filter(
                            ExternalAssetMappings.external_platform == self.platform,
                            ExternalAssetMappings.external_id == ew.id,
                        )
                        .first()
                    )

                    fallback_model = db.query(SemanticModels).filter(SemanticModels.workspace_id == clean_ws_id).first()
                    clean_model_id = fallback_model.model_id if fallback_model else "SM-001"

                    if not mapping:
                        asset = AnalyticsAssets(
                            asset_id=clean_asset_id,
                            asset_name=ew.name[:150],
                            asset_type="Workbook",
                            platform="Tableau",
                            workspace_id=clean_ws_id,
                            model_id=clean_model_id,
                            product_scope="Enterprise",
                            market_scope="Global",
                            owner_id=None,
                            lifecycle_status="legacy",
                            endorsement="none",
                            estimated_audience=50,
                            classification="internal",
                            delivery_model="business_managed",
                            synthetic_record=False,
                        )
                        db.add(asset)
                        db.flush()

                        mapping = ExternalAssetMappings(
                            external_platform=self.platform,
                            external_id=ew.id,
                            internal_asset_id=clean_asset_id,
                            workspace_or_project_id=ep.id,
                            original_name=ew.name,
                            source_connector=self.connector_id,
                            last_synced_at=now_utc,
                        )
                        db.add(mapping)
                        result.imported_reports += 1
                    else:
                        asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == mapping.internal_asset_id).first()
                        if asset:
                            asset.last_modified = now_utc
                            mapping.last_synced_at = now_utc
                            result.updated_assets += 1

            config.status = ConnectorStatus.CONNECTED.value
            config.last_synced_at = now_utc
            config.discovered_workspaces = result.imported_workspaces
            config.discovered_reports = result.imported_reports
            config.discovered_models = result.imported_models
            config.error_message = None
            db.commit()

        except Exception as e:
            db.rollback()
            logger.error("Synchronization failed for Tableau: %s", e, exc_info=True)
            result.status = ConnectorStatus.SYNC_FAILED.value
            result.errors.append(str(e))
            config.status = ConnectorStatus.SYNC_FAILED.value
            config.error_message = str(e)
            db.commit()

        result.duration_ms = round((time.time() - start_time) * 1000.0, 1)
        return result

    def _get_missing_vars(self) -> List[str]:
        missing = []
        if not self._server_url:
            missing.append("TABLEAU_SERVER_URL")
        if not self._site_name:
            missing.append("TABLEAU_SITE_NAME")
        if not self._pat_name:
            missing.append("TABLEAU_PAT_NAME")
        if not self._pat_secret:
            missing.append("TABLEAU_PAT_SECRET")
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
            auth_type="pat",
            last_tested_at=last_tested_at,
            last_synced_at=last_synced_at,
            error_message=error_msg,
            discovered_workspaces=ws_count,
            discovered_reports=rep_count,
            discovered_models=mod_count,
            required_env_vars=self.REQUIRED_ENV_VARS,
            configured_env_vars=configured,
        )

