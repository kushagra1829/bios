from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.integrations.base import (
    BaseConnector,
    ConnectorStatus,
    ConnectionTestResult,
    SyncResult,
    IntegrationStatusResponse,
)
from backend.app.integrations.powerbi.connector import PowerBiConnector
from backend.app.integrations.tableau.connector import TableauConnector


class IntegrationRegistry:
    """
    Central registry for BI Platform connectors in BIOS.
    Ensures provider-independent orchestration and uniform lifecycle management.
    """

    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {}
        # Register standard connectors
        self.register(PowerBiConnector())
        self.register(TableauConnector())

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.connector_id] = connector

    def get_connector(self, connector_id: str) -> Optional[BaseConnector]:
        return self._connectors.get(connector_id)

    def list_connectors(self) -> List[BaseConnector]:
        return list(self._connectors.values())

    def get_all_statuses(self, db: Optional[Session] = None) -> List[IntegrationStatusResponse]:
        return [c.get_integration_status(db=db) for c in self._connectors.values()]

    def test_connector(self, connector_id: str) -> ConnectionTestResult:
        connector = self.get_connector(connector_id)
        if not connector:
            return ConnectionTestResult(
                status=ConnectorStatus.NOT_CONFIGURED,
                message=f"Connector '{connector_id}' is not recognized by the integration registry.",
            )
        return connector.test_connection()

    def synchronize_connector(self, connector_id: str, db: Session, force: bool = False) -> SyncResult:
        connector = self.get_connector(connector_id)
        if not connector:
            return SyncResult(
                connector_id=connector_id,
                status="NOT_FOUND",
                errors=[f"Connector '{connector_id}' not found."],
            )
        return connector.synchronize_assets(db=db, force=force)

    def synchronize_all(self, db: Session, force: bool = False) -> Dict[str, SyncResult]:
        results = {}
        for c_id, connector in self._connectors.items():
            results[c_id] = connector.synchronize_assets(db=db, force=force)
        return results


# Global singleton registry instance
integration_registry = IntegrationRegistry()

