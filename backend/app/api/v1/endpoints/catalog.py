import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from backend.app.db.session import get_db
from backend.app.models.core import (
    Workspaces,
    Owners,
    SemanticModels,
    AnalyticsAssets,
    AssetUsage,
    LineageEdges,
)
from backend.app.models.governance import (
    KpiCatalog,
    GovernanceSignals,
    MigrationBacklog,
)
from backend.app.schemas.catalog import (
    PaginationMeta,
    PaginatedResponse,
    WorkspaceOut,
    OwnerOut,
    SemanticModelOut,
    AnalyticsAssetOut,
    AnalyticsAssetDetailOut,
    KpiOut,
    AssetUsageOut,
    LineageEdgeOut,
    GovernanceSignalOut,
    MigrationBacklogOut,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserRole, UserContext

router = APIRouter()


def paginate(query, page: int, page_size: int, db: Session):
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size
    items = db.execute(query.offset(offset).limit(page_size)).scalars().all()
    meta = PaginationMeta(total=total, page=page, page_size=page_size, pages=pages)
    return items, meta


# 1. Assets
@router.get("/assets", response_model=PaginatedResponse[AnalyticsAssetOut])
def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    limit: Optional[int] = Query(None, description="Alias for page_size"),
    skip: Optional[int] = Query(None, description="Alias for offset"),
    search: Optional[str] = Query(None, description="Search across ID, name, product, market, owner"),
    platform: Optional[str] = None,
    lifecycle_status: Optional[str] = None,
    endorsement: Optional[str] = None,
    product_scope: Optional[str] = None,
    owner_id: Optional[str] = None,
    unowned_only: bool = False,
    scoped: bool = False,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    eff_page_size = limit if limit is not None else page_size
    eff_page = page
    if skip is not None and eff_page_size > 0:
        eff_page = (skip // eff_page_size) + 1

    query = select(AnalyticsAssets)
    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            (AnalyticsAssets.asset_id.ilike(s))
            | (AnalyticsAssets.asset_name.ilike(s))
            | (AnalyticsAssets.product_scope.ilike(s))
            | (AnalyticsAssets.market_scope.ilike(s))
            | (AnalyticsAssets.owner_id.ilike(s))
        )
    if platform:
        query = query.where(AnalyticsAssets.platform == platform)
    if lifecycle_status:
        query = query.where(AnalyticsAssets.lifecycle_status == lifecycle_status)
    if endorsement:
        query = query.where(AnalyticsAssets.endorsement == endorsement)
    if product_scope:
        query = query.where(AnalyticsAssets.product_scope == product_scope)
    if unowned_only:
        query = query.where(AnalyticsAssets.owner_id == None)
    if owner_id:
        target_owner = user.actor_id if owner_id.lower() == "me" else owner_id
        query = query.where(AnalyticsAssets.owner_id == target_owner)
    elif scoped:
        if user.role == UserRole.ASSET_OWNER and user.assigned_asset_ids:
            query = query.where(AnalyticsAssets.asset_id.in_(user.assigned_asset_ids))
        elif user.role == UserRole.DOMAIN_STEWARD and user.assigned_domains:
            query = query.where(
                (AnalyticsAssets.market_scope.in_(user.assigned_domains))
                | (AnalyticsAssets.product_scope.in_(user.assigned_domains))
            )

    query = query.order_by(AnalyticsAssets.asset_id)
    items, meta = paginate(query, eff_page, eff_page_size, db)

    # Populate owner_name if available
    enriched_items = []
    for item in items:
        out = AnalyticsAssetOut.model_validate(item)
        if hasattr(item, "owner") and item.owner:
            out.owner_name = item.owner.owner_name
        enriched_items.append(out)

    return PaginatedResponse[AnalyticsAssetOut](items=enriched_items, meta=meta)


@router.get("/assets/{asset_id}", response_model=AnalyticsAssetDetailOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.execute(select(AnalyticsAssets).where(AnalyticsAssets.asset_id == asset_id)).scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found",
        )
    return asset


# 2. Workspaces
@router.get("/workspaces", response_model=PaginatedResponse[WorkspaceOut])
def list_workspaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    governance_mode: Optional[str] = None,
    scope: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(Workspaces)
    if governance_mode:
        query = query.where(Workspaces.governance_mode == governance_mode)
    if scope:
        query = query.where(Workspaces.scope == scope)
    query = query.order_by(Workspaces.workspace_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[WorkspaceOut](items=items, meta=meta)


# 3. Owners
@router.get("/owners", response_model=PaginatedResponse[OwnerOut])
def list_owners(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    role: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(Owners)
    if status_filter:
        query = query.where(Owners.status == status_filter)
    if role:
        query = query.where(Owners.role == role)
    query = query.order_by(Owners.owner_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[OwnerOut](items=items, meta=meta)


# 4. Semantic Models
@router.get("/semantic-models", response_model=PaginatedResponse[SemanticModelOut])
def list_semantic_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ai_readiness: Optional[str] = None,
    refresh_status: Optional[str] = None,
    product_scope: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(SemanticModels)
    if ai_readiness:
        query = query.where(SemanticModels.ai_readiness == ai_readiness)
    if refresh_status:
        query = query.where(SemanticModels.refresh_status == refresh_status)
    if product_scope:
        query = query.where(SemanticModels.product_scope == product_scope)
    query = query.order_by(SemanticModels.model_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[SemanticModelOut](items=items, meta=meta)


# 5. KPIs
@router.get("/kpis", response_model=PaginatedResponse[KpiOut])
def list_kpis(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    domain: Optional[str] = None,
    approval_status: Optional[str] = None,
    definition_status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(KpiCatalog)
    if domain:
        query = query.where(KpiCatalog.domain == domain)
    if approval_status:
        query = query.where(KpiCatalog.approval_status == approval_status)
    if definition_status:
        query = query.where(KpiCatalog.definition_status == definition_status)
    query = query.order_by(KpiCatalog.kpi_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[KpiOut](items=items, meta=meta)


# 6. Asset Usage
@router.get("/asset-usage", response_model=PaginatedResponse[AssetUsageOut])
def list_asset_usage(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    asset_id: Optional[str] = None,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(AssetUsage)
    if asset_id:
        query = query.where(AssetUsage.asset_id == asset_id)
    if month:
        query = query.where(AssetUsage.month == month)
    query = query.order_by(AssetUsage.asset_id, AssetUsage.month)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[AssetUsageOut](items=items, meta=meta)


# 7. Lineage Edges
@router.get("/lineage", response_model=PaginatedResponse[LineageEdgeOut])
def list_lineage(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    edge_type: Optional[str] = None,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(LineageEdges)
    if edge_type:
        query = query.where(LineageEdges.edge_type == edge_type)
    if source_id:
        query = query.where(LineageEdges.source_id == source_id)
    if target_id:
        query = query.where(LineageEdges.target_id == target_id)
    query = query.order_by(LineageEdges.source_id, LineageEdges.target_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[LineageEdgeOut](items=items, meta=meta)


# 8. Governance Signals
@router.get("/governance-signals", response_model=PaginatedResponse[GovernanceSignalOut])
def list_governance_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    signal_code: Optional[str] = None,
    severity: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    asset_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = select(GovernanceSignals)
    if signal_code:
        query = query.where(GovernanceSignals.signal_code == signal_code)
    if severity:
        query = query.where(GovernanceSignals.severity == severity)
    if status_filter:
        query = query.where(GovernanceSignals.status == status_filter)
    if asset_id:
        query = query.where(GovernanceSignals.asset_id == asset_id)
    query = query.order_by(GovernanceSignals.signal_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[GovernanceSignalOut](items=items, meta=meta)


# 9. Migration Backlog
@router.get("/migration-backlog", response_model=PaginatedResponse[MigrationBacklogOut])
def list_migration_backlog(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    recommended_path: Optional[str] = Query(None, alias="recommended_path_candidate"),
    complexity: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    query = select(MigrationBacklog)
    if recommended_path:
        query = query.where(MigrationBacklog.recommended_path_candidate == recommended_path)
    if complexity:
        query = query.where(MigrationBacklog.complexity == complexity)
    if status_filter:
        query = query.where(MigrationBacklog.status == status_filter)
    query = query.order_by(MigrationBacklog.source_asset_id)
    items, meta = paginate(query, page, page_size, db)
    return PaginatedResponse[MigrationBacklogOut](items=items, meta=meta)

