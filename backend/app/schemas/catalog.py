from datetime import datetime
from typing import Optional, List, Generic, TypeVar, Any
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    meta: PaginationMeta


# 1. Workspaces
class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    workspace_name: str
    scope: str
    environment: str
    platform: str
    governance_mode: str
    classification: str
    synthetic_record: bool


# 2. Owners
class OwnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner_id: str
    owner_name: str
    role: str
    scope: str
    status: str
    email: str
    synthetic_record: bool


# 3. Semantic Models
class SemanticModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    model_name: str
    workspace_id: str
    product_scope: str
    region_scope: str
    model_type: str
    endorsement: str
    refresh_frequency: str
    refresh_status: str
    owner_id: str
    table_count: int
    measure_count: int
    ai_readiness: str
    ai_issue_pattern: str
    synthetic_record: bool


# 4. Analytics Assets
class AnalyticsAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    asset_name: str
    asset_type: str
    platform: str
    workspace_id: str
    model_id: str
    product_scope: str
    market_scope: str
    owner_id: Optional[str] = None
    created_date: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    lifecycle_status: str
    endorsement: str
    estimated_audience: int
    classification: str
    delivery_model: str
    synthetic_record: bool


class AnalyticsAssetDetailOut(AnalyticsAssetOut):
    workspace: Optional[WorkspaceOut] = None
    owner: Optional[OwnerOut] = None
    semantic_model: Optional[SemanticModelOut] = None


# 5. KPIs
class KpiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kpi_id: str
    kpi_name: str
    canonical_metric: bool
    domain: str
    unit: str
    definition_status: str
    approval_status: str
    default_frequency: str
    business_criticality: str
    owner_id: str
    description: str
    synthetic_record: bool


# 6. Asset Usage
class AssetUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    month: str
    views: int
    unique_users: int
    exports: int
    subscriptions: int
    avg_load_ms: int
    query_errors: int
    synthetic_record: bool


# 7. Lineage Edges
class LineageEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    target_id: str
    edge_type: str
    relationship: str
    synthetic_record: bool


# 8. Governance Signals
class GovernanceSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_id: str
    asset_id: str
    signal_code: str
    severity: str
    status: str
    detected_by: str
    synthetic_record: bool


# 9. Migration Backlog
class MigrationBacklogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_asset_id: str
    product_scope: str
    market_scope: str
    recommended_path_candidate: str
    candidate_target_model_id: str
    complexity: str
    status: str
    synthetic_reason: str
    synthetic_record: bool


# 10. Ingestion Status & Trigger
class IngestionReportOut(BaseModel):
    import_id: str
    file_path: str
    file_hash: str
    dry_run: bool
    status: str
    started_at: str
    completed_at: Optional[str] = None
    total_records: int
    total_inserted: int
    total_updated: int
    total_unchanged: int
    total_rejected: int
    sheet_stats: dict
    validation_errors_count: int

