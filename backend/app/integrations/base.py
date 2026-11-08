from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session


class ConnectorStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONNECTED = "CONNECTED"
    AUTH_FAILED = "AUTH_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    SYNC_FAILED = "SYNC_FAILED"


class PlatformType(str, Enum):
    POWER_BI = "Power BI"
    TABLEAU = "Tableau"


@dataclass
class ConnectionTestResult:
    status: ConnectorStatus
    message: str
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalWorkspace:
    id: str
    name: str
    platform: str
    description: Optional[str] = None
    environment: str = "Production"
    capacity_id: Optional[str] = None


@dataclass
class ExternalReport:
    id: str
    name: str
    workspace_id: str
    platform: str
    dataset_id: Optional[str] = None
    web_url: Optional[str] = None
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    owner_email: Optional[str] = None
    endorsement: str = "none"
    description: Optional[str] = None


@dataclass
class ExternalSemanticModel:
    id: str
    name: str
    workspace_id: str
    platform: str
    refresh_status: str = "healthy"
    refresh_frequency: str = "daily"
    endorsement: str = "none"
    table_count: int = 1
    measure_count: int = 1
    ai_readiness: str = "good"


@dataclass
class SyncResult:
    connector_id: str
    status: str
    imported_workspaces: int = 0
    imported_reports: int = 0
    imported_models: int = 0
    updated_assets: int = 0
    skipped_assets: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class IntegrationStatusResponse:
    connector_id: str
    connector_name: str
    platform: str
    status: ConnectorStatus
    auth_type: str
    last_tested_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None
    discovered_workspaces: int = 0
    discovered_reports: int = 0
    discovered_models: int = 0
    required_env_vars: List[str] = field(default_factory=list)
    configured_env_vars: List[str] = field(default_factory=list)


class BaseConnector(ABC):
    """
    Standard provider-independent connector contract for enterprise BI platforms.
    All connectors must implement non-leaking credential handling, honest unconfigured state,
    and idempotent asset synchronization into the normalized BIOS catalogue.
    """

    @property
    @abstractmethod
    def connector_id(self) -> str:
        pass

    @property
    @abstractmethod
    def connector_name(self) -> str:
        pass

    @property
    @abstractmethod
    def platform(self) -> str:
        pass

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        """Probe authentication and connectivity against target platform API."""
        pass

    @abstractmethod
    def discover_workspaces(self) -> List[ExternalWorkspace]:
        """Fetch workspaces / projects accessible to the credentials."""
        pass

    @abstractmethod
    def discover_reports(self, workspace_id: Optional[str] = None) -> List[ExternalReport]:
        """Fetch reports / workbooks from target platform."""
        pass

    @abstractmethod
    def discover_semantic_models(self, workspace_id: Optional[str] = None) -> List[ExternalSemanticModel]:
        """Fetch datasets / published data sources."""
        pass

    @abstractmethod
    def fetch_asset_metadata(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Fetch deep metadata for a specific external asset."""
        pass

    @abstractmethod
    def synchronize_assets(self, db: Session, force: bool = False) -> SyncResult:
        """Synchronize external assets idempotently into the BIOS catalogue."""
        pass

    @abstractmethod
    def get_integration_status(self, db: Optional[Session] = None) -> IntegrationStatusResponse:
        """Return truthful status disclosure including unconfigured/configured variables."""
        pass

