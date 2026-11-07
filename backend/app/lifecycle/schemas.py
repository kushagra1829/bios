from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class LifecycleAction(str, Enum):
    KEEP = "KEEP"
    IMPROVE = "IMPROVE"
    CONSOLIDATE = "CONSOLIDATE"
    REVIEW = "REVIEW"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"
    MIGRATE = "MIGRATE"


class MigrationAction(str, Enum):
    MIGRATE = "MIGRATE"
    CONSOLIDATE_BEFORE_MIGRATION = "CONSOLIDATE_BEFORE_MIGRATION"
    RETIRE_INSTEAD_OF_MIGRATE = "RETIRE_INSTEAD_OF_MIGRATE"
    FIX_BEFORE_MIGRATION = "FIX_BEFORE_MIGRATION"
    HOLD_FOR_REVIEW = "HOLD_FOR_REVIEW"


class LifecycleScoreBreakdown(BaseModel):
    usage_score: float = Field(ge=0.0, le=100.0, description="Monthly views, users, and execution reliability")
    audience_reach_score: float = Field(ge=0.0, le=100.0, description="Estimated audience reach and criticality boost")
    governance_trust_score: float = Field(ge=0.0, le=100.0, description="Endorsement and active owner accountability")
    lineage_dependency_score: float = Field(ge=0.0, le=100.0, description="Downstream dependent assets requiring continuity")
    kpi_quality_score: float = Field(ge=0.0, le=100.0, description="Percentage of mapped KPIs that are canonical approved")
    semantic_health_score: float = Field(ge=0.0, le=100.0, description="Underlying semantic model AI readiness and refresh status")
    composite_score: float = Field(ge=0.0, le=100.0, description="Overall weighted health and value score")


class LifecycleRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: str
    run_id: str
    asset_id: str
    asset_name: Optional[str] = None
    platform: Optional[str] = None
    current_lifecycle_state: str
    recommended_action: str
    composite_score: float
    confidence: float
    score_breakdown: LifecycleScoreBreakdown
    explanation: str
    risks_and_dependencies: List[str] = Field(default_factory=list)
    approval_required: bool
    evidence_references: Dict[str, Any] = Field(default_factory=dict)
    assessed_at: datetime


class MigrationAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    migration_id: str
    run_id: str
    source_asset_id: str
    source_asset_name: Optional[str] = None
    recommended_action: str
    business_value: str
    technical_complexity: str
    candidate_target_model_id: Optional[str] = None
    semantic_model_readiness: str
    kpi_compatibility_score: float
    downstream_dependency_count: int
    rationalization_rationale: str
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    approval_required: bool
    assessed_at: datetime


class LifecycleSummaryOut(BaseModel):
    total_assets_assessed: int
    actions_breakdown: Dict[str, int]
    avg_composite_score: float
    assets_blocked_by_dependencies: int
    unowned_assets: int
    high_value_governance_risks: int
    rationalization_opportunities: int
    latest_run_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class MigrationSummaryOut(BaseModel):
    total_tableau_assets: int
    actions_breakdown: Dict[str, int]
    complexity_breakdown: Dict[str, int]
    direct_migrate_count: int
    consolidate_count: int
    retire_instead_count: int
    fix_before_migrate_count: int
    hold_review_count: int
    estimated_effort_reduction_pct: float
    candidate_target_models: List[str]


class LifecycleEvaluationRunSummary(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_assessed: int
    lifecycle_breakdown: Dict[str, int]
    migration_breakdown: Dict[str, int]
    execution_time_ms: float

