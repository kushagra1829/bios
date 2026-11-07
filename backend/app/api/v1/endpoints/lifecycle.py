import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.lifecycle.engine import lifecycle_engine
from backend.app.lifecycle.schemas import (
    LifecycleEvaluationRunSummary,
    LifecycleSummaryOut,
    LifecycleRecommendationOut,
    MigrationSummaryOut,
    MigrationAssessmentOut,
    LifecycleScoreBreakdown,
)
from backend.app.models.lifecycle import (
    LifecycleEvaluationRuns,
    LifecycleAssetAssessments,
    MigrationAssessments,
)
from backend.app.models.core import AnalyticsAssets

router = APIRouter()


@router.post("/evaluate", response_model=LifecycleEvaluationRunSummary, status_code=status.HTTP_200_OK)
def trigger_lifecycle_evaluation(
    db: Session = Depends(get_db),
):
    """
    Trigger full lifecycle scoring across all 360 analytics assets and migration rationalisation
    for all 94 legacy Tableau assets. Persists evaluation runs and individual assessments.
    """
    try:
        summary = lifecycle_engine.evaluate_all(db)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lifecycle evaluation failed: {str(e)}",
        )


@router.get("/summary", response_model=LifecycleSummaryOut)
def get_lifecycle_summary(
    db: Session = Depends(get_db),
):
    """
    Estate-level summary of analytics lifecycle health, recommended actions,
    assets blocked by dependencies, unowned assets, and rationalization opportunities.
    """
    return lifecycle_engine.get_lifecycle_summary(db)


@router.get("/recommendations", response_model=List[LifecycleRecommendationOut])
def list_lifecycle_recommendations(
    action: Optional[str] = Query(None, description="Filter by recommended action (KEEP, IMPROVE, CONSOLIDATE, REVIEW, RETIRE_CANDIDATE, MIGRATE)"),
    lifecycle_state: Optional[str] = Query(None, description="Filter by current state (active, candidate_retire, legacy)"),
    asset_id: Optional[str] = Query(None, description="Filter by asset ID (e.g. AST-0001)"),
    run_id: Optional[str] = Query(None, description="Filter by evaluation run ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List individual asset lifecycle recommendations with score breakdowns, risk flags, and explanations.
    """
    # If no run exists, trigger initial evaluation
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
        db.query(LifecycleAssetAssessments, AnalyticsAssets)
        .join(AnalyticsAssets, LifecycleAssetAssessments.asset_id == AnalyticsAssets.asset_id)
        .filter(LifecycleAssetAssessments.run_id == target_run_id)
    )

    if action:
        query = query.filter(LifecycleAssetAssessments.recommended_action == action.upper())
    if lifecycle_state:
        query = query.filter(LifecycleAssetAssessments.current_lifecycle_state == lifecycle_state.lower())
    if asset_id:
        query = query.filter(LifecycleAssetAssessments.asset_id == asset_id)

    results = (
        query.order_by(
            desc(LifecycleAssetAssessments.composite_score),
            LifecycleAssetAssessments.asset_id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    out = []
    for asm, asset in results:
        risks = json.loads(asm.risks_json or "[]")
        evidence = json.loads(asm.evidence_json or "{}")
        if "score_breakdown" in evidence:
            breakdown = LifecycleScoreBreakdown(**evidence["score_breakdown"])
        else:
            breakdown = LifecycleScoreBreakdown(
                usage_score=asm.usage_score,
                audience_reach_score=min(100.0, float(evidence.get("reach", {}).get("estimated_audience", 0) / 15.0)),
                governance_trust_score=asm.governance_score,
                lineage_dependency_score=asm.lineage_score,
                kpi_quality_score=asm.kpi_score,
                semantic_health_score=asm.semantic_score,
                composite_score=asm.composite_score,
            )
        out.append(
            LifecycleRecommendationOut(
                assessment_id=asm.assessment_id,
                run_id=asm.run_id,
                asset_id=asm.asset_id,
                asset_name=asset.asset_name,
                platform=asset.platform,
                current_lifecycle_state=asm.current_lifecycle_state,
                recommended_action=asm.recommended_action,
                composite_score=asm.composite_score,
                confidence=asm.confidence,
                score_breakdown=breakdown,
                explanation=asm.explanation,
                risks_and_dependencies=risks,
                approval_required=asm.approval_required,
                evidence_references=evidence,
                assessed_at=asm.assessed_at,
            )
        )
    return out


@router.get("/recommendations/{recommendation_id}", response_model=LifecycleRecommendationOut)
def get_single_lifecycle_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve details for a single asset lifecycle recommendation by assessment_id or asset_id.
    """
    query = (
        db.query(LifecycleAssetAssessments, AnalyticsAssets)
        .join(AnalyticsAssets, LifecycleAssetAssessments.asset_id == AnalyticsAssets.asset_id)
        .filter(
            (LifecycleAssetAssessments.assessment_id == recommendation_id)
            | (LifecycleAssetAssessments.asset_id == recommendation_id)
        )
        .order_by(LifecycleAssetAssessments.assessed_at.desc())
    )
    res = query.first()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lifecycle recommendation '{recommendation_id}' not found.",
        )

    asm, asset = res
    risks = json.loads(asm.risks_json or "[]")
    evidence = json.loads(asm.evidence_json or "{}")
    if "score_breakdown" in evidence:
        breakdown = LifecycleScoreBreakdown(**evidence["score_breakdown"])
    else:
        breakdown = LifecycleScoreBreakdown(
            usage_score=asm.usage_score,
            audience_reach_score=min(100.0, float(evidence.get("reach", {}).get("estimated_audience", 0) / 15.0)),
            governance_trust_score=asm.governance_score,
            lineage_dependency_score=asm.lineage_score,
            kpi_quality_score=asm.kpi_score,
            semantic_health_score=asm.semantic_score,
            composite_score=asm.composite_score,
        )
    return LifecycleRecommendationOut(
        assessment_id=asm.assessment_id,
        run_id=asm.run_id,
        asset_id=asm.asset_id,
        asset_name=asset.asset_name,
        platform=asset.platform,
        current_lifecycle_state=asm.current_lifecycle_state,
        recommended_action=asm.recommended_action,
        composite_score=asm.composite_score,
        confidence=asm.confidence,
        score_breakdown=breakdown,
        explanation=asm.explanation,
        risks_and_dependencies=risks,
        approval_required=asm.approval_required,
        evidence_references=evidence,
        assessed_at=asm.assessed_at,
    )
