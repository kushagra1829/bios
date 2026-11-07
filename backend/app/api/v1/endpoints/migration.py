import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.lifecycle.engine import lifecycle_engine
from backend.app.lifecycle.schemas import (
    MigrationSummaryOut,
    MigrationAssessmentOut,
)
from backend.app.models.lifecycle import (
    LifecycleEvaluationRuns,
    MigrationAssessments,
)
from backend.app.models.core import AnalyticsAssets

router = APIRouter()


@router.get("/summary", response_model=MigrationSummaryOut)
def get_migration_summary(
    db: Session = Depends(get_db),
):
    """
    Estate-level summary of Tableau modernization, avoided migration effort %,
    complexity distribution, and target semantic models.
    """
    return lifecycle_engine.get_migration_summary(db)


@router.get("/recommendations", response_model=List[MigrationAssessmentOut])
def list_migration_recommendations(
    action: Optional[str] = Query(None, description="Filter by migration action (MIGRATE, CONSOLIDATE_BEFORE_MIGRATION, RETIRE_INSTEAD_OF_MIGRATE, FIX_BEFORE_MIGRATION, HOLD_FOR_REVIEW)"),
    complexity: Optional[str] = Query(None, description="Filter by technical complexity (low, medium, high)"),
    business_value: Optional[str] = Query(None, description="Filter by business value (high, medium, low)"),
    source_asset_id: Optional[str] = Query(None, description="Filter by source asset ID (e.g. AST-0001)"),
    run_id: Optional[str] = Query(None, description="Filter by evaluation run ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List individual Tableau asset migration assessments with target models, complexity, and rationalisation rationale.
    """
    latest_run = (
        db.query(LifecycleEvaluationRuns)
        .filter(LifecycleEvaluationRuns.status == "success")
        .order_by(LifecycleEvaluationRuns.completed_at.desc())
        .first()
    )
    if not latest_run:
        lifecycle_engine.evaluate_all(db)
        latest_run = (
            db.query(LifecycleEvaluationRuns)
            .filter(LifecycleEvaluationRuns.status == "success")
            .order_by(LifecycleEvaluationRuns.completed_at.desc())
            .first()
        )

    target_run_id = run_id or latest_run.run_id
    query = (
        db.query(MigrationAssessments, AnalyticsAssets)
        .join(AnalyticsAssets, MigrationAssessments.source_asset_id == AnalyticsAssets.asset_id)
        .filter(MigrationAssessments.run_id == target_run_id)
    )

    if action:
        query = query.filter(MigrationAssessments.recommended_action == action.upper())
    if complexity:
        query = query.filter(MigrationAssessments.technical_complexity == complexity.lower())
    if business_value:
        query = query.filter(MigrationAssessments.business_value == business_value.lower())
    if source_asset_id:
        query = query.filter(MigrationAssessments.source_asset_id == source_asset_id)

    results = (
        query.order_by(MigrationAssessments.source_asset_id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    out = []
    for m, asset in results:
        blockers = json.loads(m.blockers_json or "[]")
        warnings = json.loads(m.warnings_json or "[]")
        out.append(
            MigrationAssessmentOut(
                migration_id=m.migration_id,
                run_id=m.run_id,
                source_asset_id=m.source_asset_id,
                source_asset_name=asset.asset_name,
                recommended_action=m.recommended_action,
                business_value=m.business_value,
                technical_complexity=m.technical_complexity,
                candidate_target_model_id=m.candidate_target_model_id,
                semantic_model_readiness=m.semantic_model_readiness,
                kpi_compatibility_score=m.kpi_compatibility_score,
                downstream_dependency_count=m.downstream_dependency_count,
                rationalization_rationale=m.rationalization_rationale,
                blockers=blockers,
                warnings=warnings,
                approval_required=m.approval_required,
                assessed_at=m.assessed_at,
            )
        )
    return out

