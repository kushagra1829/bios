from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.integrations.registry import integration_registry
from backend.app.integrations.base import ConnectorStatus
from backend.app.auth.dependencies import require_admin
from backend.app.auth.schemas import UserContext

router = APIRouter()


class ConnectionTestOut(BaseModel):
    status: str
    message: str
    latency_ms: Optional[float] = None
    details: dict = {}


class SyncResultOut(BaseModel):
    connector_id: str
    status: str
    imported_workspaces: int
    imported_reports: int
    imported_models: int
    updated_assets: int
    skipped_assets: int
    errors: List[str]
    duration_ms: float


class IntegrationStatusOut(BaseModel):
    connector_id: str
    connector_name: str
    platform: str
    status: str
    auth_type: str
    last_tested_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    error_message: Optional[str] = None
    discovered_workspaces: int
    discovered_reports: int
    discovered_models: int
    required_env_vars: List[str]
    configured_env_vars: List[str]


@router.get("", response_model=List[IntegrationStatusOut])
def list_integrations(db: Session = Depends(get_db), user: UserContext = Depends(require_admin)):
    """List operational status and synchronization telemetry for all BI platform connectors."""
    statuses = integration_registry.get_all_statuses(db=db)
    return [
        IntegrationStatusOut(
            connector_id=s.connector_id,
            connector_name=s.connector_name,
            platform=s.platform,
            status=s.status.value,
            auth_type=s.auth_type,
            last_tested_at=s.last_tested_at.isoformat() if s.last_tested_at else None,
            last_synced_at=s.last_synced_at.isoformat() if s.last_synced_at else None,
            error_message=s.error_message,
            discovered_workspaces=s.discovered_workspaces,
            discovered_reports=s.discovered_reports,
            discovered_models=s.discovered_models,
            required_env_vars=s.required_env_vars,
            configured_env_vars=s.configured_env_vars,
        )
        for s in statuses
    ]


@router.get("/{connector_id}", response_model=IntegrationStatusOut)
def get_integration(connector_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_admin)):
    """Fetch status and discovery details for a specific connector."""
    connector = integration_registry.get_connector(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' is not recognized.",
        )
    s = connector.get_integration_status(db=db)
    return IntegrationStatusOut(
        connector_id=s.connector_id,
        connector_name=s.connector_name,
        platform=s.platform,
        status=s.status.value,
        auth_type=s.auth_type,
        last_tested_at=s.last_tested_at.isoformat() if s.last_tested_at else None,
        last_synced_at=s.last_synced_at.isoformat() if s.last_synced_at else None,
        error_message=s.error_message,
        discovered_workspaces=s.discovered_workspaces,
        discovered_reports=s.discovered_reports,
        discovered_models=s.discovered_models,
        required_env_vars=s.required_env_vars,
        configured_env_vars=s.configured_env_vars,
    )


@router.post("/{connector_id}/test", response_model=ConnectionTestOut)
def test_integration(connector_id: str, user: UserContext = Depends(require_admin)):
    """Probe external BI platform connection and authentication."""
    connector = integration_registry.get_connector(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' is not recognized.",
        )
    res = connector.test_connection()
    return ConnectionTestOut(
        status=res.status.value,
        message=res.message,
        latency_ms=res.latency_ms,
        details=res.details,
    )


@router.post("/{connector_id}/sync", response_model=SyncResultOut)
def sync_integration(connector_id: str, force: bool = False, db: Session = Depends(get_db), user: UserContext = Depends(require_admin)):
    """Trigger manual catalogue synchronization for a specific connector."""
    connector = integration_registry.get_connector(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' is not recognized.",
        )
    res = connector.synchronize_assets(db=db, force=force)
    return SyncResultOut(
        connector_id=res.connector_id,
        status=res.status,
        imported_workspaces=res.imported_workspaces,
        imported_reports=res.imported_reports,
        imported_models=res.imported_models,
        updated_assets=res.updated_assets,
        skipped_assets=res.skipped_assets,
        errors=res.errors,
        duration_ms=res.duration_ms,
    )

