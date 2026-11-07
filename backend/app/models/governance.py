from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class KpiCatalog(Base):
    __tablename__ = "kpi_catalog"

    kpi_id = Column(String(10), primary_key=True)
    kpi_name = Column(String(100), nullable=False, index=True)
    canonical_metric = Column(Boolean, nullable=False, default=True)
    domain = Column(String(50), nullable=False, index=True)
    unit = Column(String(30), nullable=False)
    definition_status = Column(String(50), nullable=False)  # 'canonical', 'duplicate_candidate', etc.
    approval_status = Column(String(30), nullable=False)  # 'approved', 'local', 'unapproved', 'draft'
    default_frequency = Column(String(30), nullable=False)
    business_criticality = Column(String(30), nullable=False)  # 'high', 'medium', 'critical'
    owner_id = Column(String(10), ForeignKey("owners.owner_id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    # Relationships
    owner = relationship("Owners")
    asset_mappings = relationship("AssetKpiMap", back_populates="kpi", cascade="all, delete-orphan")


class AssetKpiMap(Base):
    __tablename__ = "asset_kpi_map"

    asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    kpi_id = Column(String(10), ForeignKey("kpi_catalog.kpi_id", ondelete="CASCADE"), nullable=False, index=True)
    usage_role = Column(String(30), nullable=False)  # 'primary', 'supporting', 'filter'
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("asset_id", "kpi_id"),
    )

    asset = relationship("AnalyticsAssets", back_populates="kpi_mappings")
    kpi = relationship("KpiCatalog", back_populates="asset_mappings")


class GovernanceSignals(Base):
    __tablename__ = "governance_signals"

    signal_id = Column(String(20), primary_key=True)
    asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    signal_code = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False)  # 'high', 'medium', 'low'
    status = Column(String(30), nullable=False)  # 'open', 'acknowledged'
    detected_by = Column(String(50), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    asset = relationship("AnalyticsAssets", back_populates="governance_signals")


class MigrationBacklog(Base):
    __tablename__ = "migration_backlog"

    source_asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), primary_key=True)
    product_scope = Column(String(50), nullable=False)
    market_scope = Column(String(50), nullable=False)
    recommended_path_candidate = Column(String(50), nullable=False)  # 'RETIRE', 'MIGRATE', etc.
    candidate_target_model_id = Column(String(10), ForeignKey("semantic_models.model_id", ondelete="RESTRICT"), nullable=False, index=True)
    complexity = Column(String(20), nullable=False)  # 'low', 'medium', 'high'
    status = Column(String(30), nullable=False)  # 'assessed', 'in_progress', 'not_started'
    synthetic_reason = Column(String(100), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    source_asset = relationship("AnalyticsAssets", back_populates="migration_backlog_item")
    candidate_target_model = relationship("SemanticModels")


class DataQuality(Base):
    """
    Polymorphic benchmark catalog of injected schema defects.
    record_id maps to SemanticModels (SM-xxx) or AnalyticsAssets (AST-xxx).
    """
    __tablename__ = "data_quality"

    issue_id = Column(String(20), primary_key=True)
    sheet = Column(String(50), nullable=False, index=True)
    record_id = Column(String(20), nullable=False, index=True)
    field = Column(String(50), nullable=False)
    issue_value = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False)  # 'high', 'medium', 'low'
    impact = Column(Text, nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)


class GovernanceRules(Base):
    __tablename__ = "governance_rules"

    rule_id = Column(String(20), primary_key=True)
    rule_name = Column(String(100), nullable=False)
    rule_description = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False)  # 'high', 'medium'


class BusinessRequests(Base):
    __tablename__ = "business_requests"

    request_id = Column(String(20), primary_key=True)
    request_date = Column(DateTime, nullable=False)
    product_context = Column(String(50), nullable=False, index=True)
    market_context = Column(String(50), nullable=False, index=True)
    request_text = Column(Text, nullable=False)
    urgency = Column(String(20), nullable=False)  # 'normal', 'high', 'urgent'
    status = Column(String(30), nullable=False)  # 'new', 'triaged'
    synthetic_record = Column(Boolean, nullable=False, default=True)


class GovernanceEvaluationRuns(Base):
    __tablename__ = "governance_evaluation_runs"

    run_id = Column(String(50), primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(30), nullable=False, default="in_progress")  # 'success', 'failed', 'in_progress'
    total_findings = Column(Integer, nullable=False, default=0)
    critical_count = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    info_count = Column(Integer, nullable=False, default=0)
    summary_json = Column(Text, nullable=True)

    findings = relationship("GovernanceFindings", back_populates="evaluation_run", cascade="all, delete-orphan")


class GovernanceFindings(Base):
    __tablename__ = "governance_findings"

    finding_id = Column(String(64), primary_key=True)
    run_id = Column(String(50), ForeignKey("governance_evaluation_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String(20), nullable=False, index=True)
    target_entity_type = Column(String(50), nullable=False, index=True)  # 'asset', 'model', 'kpi', 'request'
    target_entity_id = Column(String(50), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, index=True)  # 'critical', 'high', 'medium', 'low', 'info'
    status = Column(String(30), nullable=False, default="open", index=True)  # 'open', 'persisting', 'resolved', 'acknowledged'
    title = Column(String(255), nullable=False)
    explanation = Column(Text, nullable=False)
    observed_value = Column(Text, nullable=True)
    expected_condition = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=False)
    human_approval_required = Column(Boolean, nullable=False, default=True)
    evidence_json = Column(Text, nullable=False)
    detected_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    evaluation_run = relationship("GovernanceEvaluationRuns", back_populates="findings")

    __table_args__ = (
        Index("ix_finding_rule_target", "rule_id", "target_entity_type", "target_entity_id"),
    )


