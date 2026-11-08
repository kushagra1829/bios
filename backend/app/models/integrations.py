from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class IntegrationConfigs(Base):
    """
    Configuration and operational status for external BI connectors (Power BI, Tableau).
    Never stores plain secrets in the database.
    """
    __tablename__ = "integration_configs"

    connector_id = Column(String(50), primary_key=True)  # 'powerbi', 'tableau'
    connector_name = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="NOT_CONFIGURED")  # 'NOT_CONFIGURED', 'CONNECTED', 'AUTH_FAILED', 'PERMISSION_DENIED', 'SYNC_FAILED'
    auth_type = Column(String(50), nullable=False, default="service_principal")  # 'service_principal', 'pat', 'oauth'
    endpoint_url = Column(String(255), nullable=True)
    tenant_id = Column(String(100), nullable=True)
    client_id = Column(String(100), nullable=True)
    site_name = Column(String(100), nullable=True)
    target_workspace_filter = Column(String(255), nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    discovered_workspaces = Column(Integer, nullable=False, default=0)
    discovered_reports = Column(Integer, nullable=False, default=0)
    discovered_models = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ExternalAssetMappings(Base):
    """
    Bi-directional mapping between internal BIOS assets and external BI platform objects.
    Maintains provenance and prevents duplicate ingestion during repeated synchronizations.
    """
    __tablename__ = "external_asset_mappings"

    external_platform = Column(String(50), nullable=False)  # 'Power BI', 'Tableau'
    external_id = Column(String(150), nullable=False)
    internal_asset_id = Column(String(20), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_or_project_id = Column(String(100), nullable=True)
    original_name = Column(String(255), nullable=False)
    source_connector = Column(String(50), nullable=False)
    last_synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    raw_metadata_json = Column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("external_platform", "external_id"),
        Index("ix_external_asset_lookup", "external_platform", "external_id"),
    )

    asset = relationship("AnalyticsAssets")

