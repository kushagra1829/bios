from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class Workspaces(Base):
    __tablename__ = "workspaces"

    workspace_id = Column(String(10), primary_key=True)
    workspace_name = Column(String(100), nullable=False)
    scope = Column(String(30), nullable=False)
    environment = Column(String(30), nullable=False)
    platform = Column(String(30), nullable=False, default="Power BI")
    governance_mode = Column(String(50), nullable=False)
    classification = Column(String(30), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    # Relationships
    semantic_models = relationship("SemanticModels", back_populates="workspace", cascade="all, delete-orphan")
    analytics_assets = relationship("AnalyticsAssets", back_populates="workspace", cascade="all, delete-orphan")


class Owners(Base):
    __tablename__ = "owners"

    owner_id = Column(String(10), primary_key=True)
    owner_name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)
    scope = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)  # 'active', 'inactive'
    email = Column(String(100), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    # Relationships
    semantic_models = relationship("SemanticModels", back_populates="owner")
    analytics_assets = relationship("AnalyticsAssets", back_populates="owner")


class SemanticModels(Base):
    __tablename__ = "semantic_models"

    model_id = Column(String(10), primary_key=True)
    model_name = Column(String(100), nullable=False)
    workspace_id = Column(String(10), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False, index=True)
    product_scope = Column(String(50), nullable=False, index=True)
    region_scope = Column(String(50), nullable=False, index=True)
    model_type = Column(String(50), nullable=False, default="Power BI semantic model")
    endorsement = Column(String(30), nullable=False)  # 'certified', 'promoted', 'none'
    refresh_frequency = Column(String(30), nullable=False)  # 'daily', 'weekly', 'monthly'
    refresh_status = Column(String(30), nullable=False)  # 'healthy', 'warning', 'failed'
    owner_id = Column(String(10), ForeignKey("owners.owner_id", ondelete="RESTRICT"), nullable=False, index=True)
    table_count = Column(Integer, nullable=False)
    measure_count = Column(Integer, nullable=False)
    ai_readiness = Column(String(30), nullable=False)  # 'good', 'partial', 'poor'
    ai_issue_pattern = Column(String(50), nullable=False)  # 'clear', 'poor_names', etc.
    synthetic_record = Column(Boolean, nullable=False, default=True)

    # Relationships
    workspace = relationship("Workspaces", back_populates="semantic_models")
    owner = relationship("Owners", back_populates="semantic_models")
    analytics_assets = relationship("AnalyticsAssets", back_populates="semantic_model", cascade="all, delete-orphan")


class AnalyticsAssets(Base):
    __tablename__ = "analytics_assets"

    asset_id = Column(String(10), primary_key=True)
    asset_name = Column(String(150), nullable=False, index=True)
    asset_type = Column(String(50), nullable=False)  # 'Report', 'Workbook', 'App', 'Dashboard'
    platform = Column(String(50), nullable=False)  # 'Power BI', 'Tableau'
    workspace_id = Column(String(10), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False, index=True)
    model_id = Column(String(10), ForeignKey("semantic_models.model_id", ondelete="RESTRICT"), nullable=False, index=True)
    product_scope = Column(String(50), nullable=False, index=True)
    market_scope = Column(String(50), nullable=False, index=True)
    # CRITICAL: owner_id is NULL for exactly 21 unowned assets. Do NOT make this NOT NULL.
    owner_id = Column(String(10), ForeignKey("owners.owner_id", ondelete="SET NULL"), nullable=True, index=True)
    created_date = Column(DateTime, nullable=True)
    last_modified = Column(DateTime, nullable=True)
    lifecycle_status = Column(String(30), nullable=False)  # 'active', 'candidate_retire', 'legacy'
    endorsement = Column(String(30), nullable=False)  # 'none', 'promoted', 'certified'
    estimated_audience = Column(Integer, nullable=False)
    classification = Column(String(30), nullable=False)  # 'internal', 'confidential'
    delivery_model = Column(String(50), nullable=False)  # 'business_managed', 'central_BI', 'self_service'
    synthetic_record = Column(Boolean, nullable=False, default=True)

    # Relationships
    workspace = relationship("Workspaces", back_populates="analytics_assets")
    semantic_model = relationship("SemanticModels", back_populates="analytics_assets")
    owner = relationship("Owners", back_populates="analytics_assets")
    usage_records = relationship("AssetUsage", back_populates="asset", cascade="all, delete-orphan")
    kpi_mappings = relationship("AssetKpiMap", back_populates="asset", cascade="all, delete-orphan")
    governance_signals = relationship("GovernanceSignals", back_populates="asset", cascade="all, delete-orphan")
    migration_backlog_item = relationship("MigrationBacklog", back_populates="source_asset", uselist=False, cascade="all, delete-orphan")


class AssetUsage(Base):
    __tablename__ = "asset_usage"

    asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    views = Column(Integer, nullable=False, default=0)
    unique_users = Column(Integer, nullable=False, default=0)
    exports = Column(Integer, nullable=False, default=0)
    subscriptions = Column(Integer, nullable=False, default=0)
    avg_load_ms = Column(Integer, nullable=False, default=0)
    query_errors = Column(Integer, nullable=False, default=0)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("asset_id", "month"),
    )

    asset = relationship("AnalyticsAssets", back_populates="usage_records")


class LineageEdges(Base):
    """
    Polymorphic DAG edges.
    source_id and target_id reference either SemanticModels (SM-xxx) or AnalyticsAssets (AST-xxx).
    No artificial single-table foreign key is enforced on polymorphic node identifiers.
    """
    __tablename__ = "lineage_edges"

    source_id = Column(String(20), nullable=False, index=True)
    target_id = Column(String(20), nullable=False, index=True)
    edge_type = Column(String(50), nullable=False)  # 'MODEL_TO_ASSET', 'ASSET_TO_ASSET', 'MODEL_TO_MODEL'
    relationship = Column(String(100), nullable=False)  # 'semantic dependency', etc.
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("source_id", "target_id"),
        Index("ix_lineage_target_source", "target_id", "source_id"),
    )

