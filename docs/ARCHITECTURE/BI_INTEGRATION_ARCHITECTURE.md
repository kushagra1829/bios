# BIOS BI Integration Architecture & Metadata Synchronization Specification

**Milestones:** 5.11 + 5.12  
**Status:** Implemented & Validated  
**Author:** Principal Enterprise Software Architect & BI Integration Specialist  
**Dataset Digest:** `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab`  

---

## 1. Executive Summary

Milestones 5.11 and 5.12 transition BIOS from an application dependent purely on pre-seeded synthetic data packs to an **enterprise-ready, provider-independent BI integration platform**.

The integration layer interfaces with Microsoft Power BI and Tableau Server / Cloud through standardized REST APIs, normalizing disparate external assets into the common BIOS asset catalogue while strictly preserving the pristine synthetic challenge benchmark dataset.

---

## 2. Architectural Design & Connector Abstraction

### 2.1 Provider-Independent Connector Contract
All BI connectors inherit from `BaseConnector` (`backend/app/integrations/base.py`), establishing consistent lifecycle and security behavior:

```python
class BaseConnector(ABC):
    @property
    def connector_id(self) -> str: ...
    @property
    def connector_name(self) -> str: ...
    @property
    def platform(self) -> str: ...

    def test_connection(self) -> ConnectionTestResult: ...
    def discover_workspaces(self) -> List[ExternalWorkspace]: ...
    def discover_reports(self, workspace_id: Optional[str] = None) -> List[ExternalReport]: ...
    def discover_semantic_models(self, workspace_id: Optional[str] = None) -> List[ExternalSemanticModel]: ...
    def fetch_asset_metadata(self, external_id: str) -> Optional[Dict[str, Any]]: ...
    def synchronize_assets(self, db: Session, force: bool = False) -> SyncResult: ...
    def get_integration_status(self, db: Optional[Session] = None) -> IntegrationStatusResponse: ...
```

### 2.2 Central Integration Registry
`IntegrationRegistry` (`backend/app/integrations/registry.py`) manages connector instances, providing uniform dispatch for multi-platform synchronization, diagnostics, and status reporting without coupling endpoints to specific vendors.

---

## 3. Microsoft Power BI Connector

### 3.1 Authentication & Microsoft Entra ID
The Power BI connector (`backend/app/integrations/powerbi/connector.py`) authenticates using Microsoft Entra ID (Azure AD) Service Principal OAuth 2.0 client credentials:

- **Token Endpoint:** `https://login.microsoftonline.com/{POWERBI_TENANT_ID}/oauth2/v2.0/token`
- **Scope:** `https://analysis.windows.net/powerbi/api/.default`
- **Grant Type:** `client_credentials`
- **Session Caching:** Tokens are cached in-memory with automatic refresh prior to expiration (`expires_in`). Tokens are never persisted to disk or emitted in logs.

### 3.2 Power BI REST API Endpoints
- **Workspaces:** `GET https://api.powerbi.com/v1.0/myorg/groups`
- **Reports:** `GET https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports`
- **Datasets:** `GET https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets`

### 3.3 Security & Safe Handling
- **Missing Credentials:** If `POWERBI_TENANT_ID`, `POWERBI_CLIENT_ID`, or `POWERBI_CLIENT_SECRET` are unset, the connector reports status `NOT_CONFIGURED` and explicitly enumerates the required configuration variables.
- **Throttling (429):** Reads `Retry-After` headers and yields `SYNC_FAILED` with explicit retry latency.
- **Permission Errors (401/403):** Translates into `AUTH_FAILED` or `PERMISSION_DENIED` with actionable advice (e.g., verifying `Tenant.Read.All` admin privileges).

---

## 4. Tableau Server / Cloud Connector

### 4.1 Authentication & Personal Access Tokens
The Tableau connector (`backend/app/integrations/tableau/connector.py`) supports Tableau REST API 3.x using Personal Access Tokens (PAT):

- **Sign-in Endpoint:** `POST {TABLEAU_SERVER_URL}/api/{version}/auth/signin`
- **Session Header:** Returns `X-Tableau-Auth` token and site ID.
- **Required Variables:** `TABLEAU_SERVER_URL`, `TABLEAU_SITE_NAME`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_SECRET`.

### 4.2 Discovery & Metadata Endpoints
- **Projects:** `GET /api/{version}/sites/{site_id}/projects` $\rightarrow$ Mapped to `Workspaces`
- **Workbooks:** `GET /api/{version}/sites/{site_id}/workbooks` $\rightarrow$ Mapped to `AnalyticsAssets`
- **Published Datasources:** `GET /api/{version}/sites/{site_id}/datasources` $\rightarrow$ Mapped to `SemanticModels`

---

## 5. Normalized Asset Catalogue & Idempotency

### 5.1 Dual-Class Asset Distinction
To satisfy the coding-agent contract, BIOS cleanly segregates synthetic challenge baseline data from dynamically ingested external assets:

- **Synthetic Challenge Records:** `synthetic_record = True` (exactly 360 assets, 75 models, 16 workspaces).
- **Imported Integration Records:** `synthetic_record = False`.

### 5.2 External Asset Mapping Table
Every imported object is indexed in `external_asset_mappings`:

```sql
CREATE TABLE external_asset_mappings (
    external_platform VARCHAR(50) NOT NULL,
    external_id VARCHAR(150) NOT NULL,
    internal_asset_id VARCHAR(20) REFERENCES analytics_assets(asset_id),
    workspace_or_project_id VARCHAR(100),
    original_name VARCHAR(255) NOT NULL,
    source_connector VARCHAR(50) NOT NULL,
    last_synced_at TIMESTAMP NOT NULL,
    raw_metadata_json TEXT,
    PRIMARY KEY (external_platform, external_id)
);
```

### 5.3 Idempotent Upsert Rules
1. Existing external IDs match against `external_asset_mappings`.
2. Existing assets receive operational updates (`last_modified`, `last_synced_at`).
3. Manually maintained governance metadata (`product_scope`, `market_scope`, `owner_id`, `classification`) is **never** overwritten with empty external values.

