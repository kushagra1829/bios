from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class LifecycleEvaluationRuns(Base):
    __tablename__ = "lifecycle_evaluation_runs"

    run_id = Column(String(50), primary_key=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    total_assessed = Column(Integer, nullable=False, default=0)
    keep_count = Column(Integer, nullable=False, default=0)
    improve_count = Column(Integer, nullable=False, default=0)
    consolidate_count = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)
    retire_count = Column(Integer, nullable=False, default=0)
    migrate_count = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="in_progress")  # in_progress, success, failed
    summary_json = Column(Text, nullable=True)

    # Relationships
    assessments = relationship("LifecycleAssetAssessments", back_populates="run", cascade="all, delete-orphan")
    migration_assessments = relationship("MigrationAssessments", back_populates="run", cascade="all, delete-orphan")


class LifecycleAssetAssessments(Base):
    __tablename__ = "lifecycle_asset_assessments"

    assessment_id = Column(String(64), primary_key=True)
    run_id = Column(String(50), ForeignKey("lifecycle_evaluation_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    current_lifecycle_state = Column(String(30), nullable=False)
    recommended_action = Column(String(30), nullable=False, index=True)  # KEEP, IMPROVE, CONSOLIDATE, REVIEW, RETIRE_CANDIDATE, MIGRATE
    composite_score = Column(Float, nullable=False, default=0.0)
    confidence = Column(Float, nullable=False, default=0.0)
    usage_score = Column(Float, nullable=False, default=0.0)
    governance_score = Column(Float, nullable=False, default=0.0)
    lineage_score = Column(Float, nullable=False, default=0.0)
    kpi_score = Column(Float, nullable=False, default=0.0)
    semantic_score = Column(Float, nullable=False, default=0.0)
    explanation = Column(Text, nullable=False)
    risks_json = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=True)
    assessed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("LifecycleEvaluationRuns", back_populates="assessments")
    asset = relationship("AnalyticsAssets")

    __table_args__ = (
        Index("ix_lifecycle_action_asset", "recommended_action", "asset_id"),
    )


class MigrationAssessments(Base):
    __tablename__ = "migration_assessments"

    migration_id = Column(String(64), primary_key=True)
    run_id = Column(String(50), ForeignKey("lifecycle_evaluation_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    source_asset_id = Column(String(10), ForeignKey("analytics_assets.asset_id", ondelete="CASCADE"), nullable=False, index=True)
    recommended_action = Column(String(50), nullable=False, index=True)  # MIGRATE, CONSOLIDATE_BEFORE_MIGRATION, RETIRE_INSTEAD_OF_MIGRATE, FIX_BEFORE_MIGRATION, HOLD_FOR_REVIEW
    business_value = Column(String(30), nullable=False)  # high, medium, low
    technical_complexity = Column(String(30), nullable=False)  # low, medium, high
    candidate_target_model_id = Column(String(10), nullable=True)
    semantic_model_readiness = Column(String(30), nullable=False)  # good, partial, poor
    kpi_compatibility_score = Column(Float, nullable=False, default=0.0)
    downstream_dependency_count = Column(Integer, nullable=False, default=0)
    rationalization_rationale = Column(Text, nullable=False)
    blockers_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=True)
    assessed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("LifecycleEvaluationRuns", back_populates="migration_assessments")
    source_asset = relationship("AnalyticsAssets")

