import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.lifecycle.schemas import (
    LifecycleAction,
    MigrationAction,
    LifecycleScoreBreakdown,
    LifecycleRecommendationOut,
    MigrationAssessmentOut,
    LifecycleSummaryOut,
    MigrationSummaryOut,
    LifecycleEvaluationRunSummary,
)
from backend.app.lifecycle.scoring import scoring_engine
from backend.app.lifecycle.rules import lifecycle_rules
from backend.app.lifecycle.migration import migration_engine
from backend.app.models.core import AnalyticsAssets, LineageEdges
from backend.app.models.lifecycle import (
    LifecycleEvaluationRuns,
    LifecycleAssetAssessments,
    MigrationAssessments,
)

logger = logging.getLogger(__name__)


class LifecycleEngine:
    """
    Lifecycle & Migration Intelligence Engine for BIOS.
    Orchestrates estate-wide lifecycle scoring and Tableau migration rationalisation.
    Persists evaluation runs and assessments for human audit and governance workflows.
    """

    def evaluate_all(self, db: Session, run_id: Optional[str] = None) -> LifecycleEvaluationRunSummary:
        """
        Execute full lifecycle scoring across all 360 assets and migration assessment across all 94 Tableau assets.
        Transactional, idempotent, and audit-ready.
        """
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)
        run_id = run_id or f"LIFECYCLE-RUN-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        logger.info(f"[LifecycleEngine] Starting evaluation run {run_id}")

        eval_run = LifecycleEvaluationRuns(
            run_id=run_id,
            started_at=now_utc,
            status="in_progress",
        )
        db.add(eval_run)
        db.flush()

        try:
            # Precompute downstream lineage dependencies for all assets
            downstream_counts = dict(
                db.query(LineageEdges.source_id, func.count(LineageEdges.target_id))
                .filter(LineageEdges.edge_type == "ASSET_TO_ASSET")
                .group_by(LineageEdges.source_id)
                .all()
            )

            all_assets = (
                db.query(AnalyticsAssets)
                .order_by(AnalyticsAssets.asset_id.asc())
                .all()
            )

            action_counts = {action.value: 0 for action in LifecycleAction}

            # 1. Evaluate Lifecycle for all assets
            for asset in all_assets:
                dep_count = downstream_counts.get(asset.asset_id, 0)
                score_breakdown, evidence = scoring_engine.calculate_score(
                    asset, db, downstream_dependents_count=dep_count
                )
                evidence["score_breakdown"] = score_breakdown.model_dump(mode="json")

                action, confidence, explanation, risks, approval_required = lifecycle_rules.evaluate_asset(
                    asset, score_breakdown, evidence
                )

                action_counts[action.value] = action_counts.get(action.value, 0) + 1

                assessment_id = f"ASM-{run_id[-6:]}-{asset.asset_id}"
                assessment = LifecycleAssetAssessments(
                    assessment_id=assessment_id,
                    run_id=run_id,
                    asset_id=asset.asset_id,
                    current_lifecycle_state=asset.lifecycle_status,
                    recommended_action=action.value,
                    composite_score=score_breakdown.composite_score,
                    confidence=confidence,
                    usage_score=score_breakdown.usage_score,
                    governance_score=score_breakdown.governance_trust_score,
                    lineage_score=score_breakdown.lineage_dependency_score,
                    kpi_score=score_breakdown.kpi_quality_score,
                    semantic_score=score_breakdown.semantic_health_score,
                    explanation=explanation,
                    risks_json=json.dumps(risks),
                    evidence_json=json.dumps(evidence),
                    approval_required=approval_required,
                    assessed_at=now_utc,
                )
                db.add(assessment)

            # 2. Evaluate Migration Assessment for Tableau Assets
            migration_results = migration_engine.evaluate_tableau_assets(db)
            migration_action_counts = {action.value: 0 for action in MigrationAction}

            for m in migration_results:
                m_action = m["recommended_action"]
                migration_action_counts[m_action] = migration_action_counts.get(m_action, 0) + 1

                mig_id = f"MIG-{run_id[-6:]}-{m['source_asset_id']}"
                mig_assessment = MigrationAssessments(
                    migration_id=mig_id,
                    run_id=run_id,
                    source_asset_id=m["source_asset_id"],
                    recommended_action=m_action,
                    business_value=m["business_value"],
                    technical_complexity=m["technical_complexity"],
                    candidate_target_model_id=m["candidate_target_model_id"],
                    semantic_model_readiness=m["semantic_model_readiness"],
                    kpi_compatibility_score=m["kpi_compatibility_score"],
                    downstream_dependency_count=m["downstream_dependency_count"],
                    rationalization_rationale=m["rationalization_rationale"],
                    blockers_json=json.dumps(m["blockers"]),
                    warnings_json=json.dumps(m["warnings"]),
                    approval_required=m["approval_required"],
                    assessed_at=now_utc,
                )
                db.add(mig_assessment)

            duration_ms = (time.time() - start_time) * 1000.0
            completed_utc = datetime.now(timezone.utc)

            eval_run.status = "success"
            eval_run.completed_at = completed_utc
            eval_run.total_assessed = len(all_assets)
            eval_run.keep_count = action_counts.get(LifecycleAction.KEEP.value, 0)
            eval_run.improve_count = action_counts.get(LifecycleAction.IMPROVE.value, 0)
            eval_run.consolidate_count = action_counts.get(LifecycleAction.CONSOLIDATE.value, 0)
            eval_run.review_count = action_counts.get(LifecycleAction.REVIEW.value, 0)
            eval_run.retire_count = action_counts.get(LifecycleAction.RETIRE_CANDIDATE.value, 0)
            eval_run.migrate_count = action_counts.get(LifecycleAction.MIGRATE.value, 0)

            summary_payload = {
                "run_id": run_id,
                "status": "success",
                "started_at": now_utc.isoformat(),
                "completed_at": completed_utc.isoformat(),
                "execution_time_ms": round(duration_ms, 2),
                "total_assessed": len(all_assets),
                "lifecycle_breakdown": action_counts,
                "migration_breakdown": migration_action_counts,
            }
            eval_run.summary_json = json.dumps(summary_payload)

            db.commit()

            return LifecycleEvaluationRunSummary(
                run_id=run_id,
                status="success",
                started_at=now_utc,
                completed_at=completed_utc,
                total_assessed=len(all_assets),
                lifecycle_breakdown=action_counts,
                migration_breakdown=migration_action_counts,
                execution_time_ms=round(duration_ms, 2),
            )

        except Exception as e:
            db.rollback()
            logger.error(f"[LifecycleEngine] Evaluation run failed: {e}", exc_info=True)
            failed_run = db.query(LifecycleEvaluationRuns).filter(LifecycleEvaluationRuns.run_id == run_id).first()
            if failed_run:
                failed_run.status = "failed"
                failed_run.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise

    def get_lifecycle_summary(self, db: Session) -> LifecycleSummaryOut:
        """Portfolio-level summary across the analytics estate."""
        latest_run = (
            db.query(LifecycleEvaluationRuns)
            .filter(LifecycleEvaluationRuns.status == "success")
            .order_by(LifecycleEvaluationRuns.completed_at.desc())
            .first()
        )

        if not latest_run:
            # Auto-run if never run before
            self.evaluate_all(db)
            latest_run = (
                db.query(LifecycleEvaluationRuns)
                .filter(LifecycleEvaluationRuns.status == "success")
                .order_by(LifecycleEvaluationRuns.completed_at.desc())
                .first()
            )

        assessments = (
            db.query(LifecycleAssetAssessments)
            .filter(LifecycleAssetAssessments.run_id == latest_run.run_id)
            .all()
        )

        actions_breakdown: Dict[str, int] = {}
        total_score = 0.0
        blocked_dependencies = 0
        unowned = 0
        high_value_risks = 0
        rationalization_opps = 0

        for a in assessments:
            actions_breakdown[a.recommended_action] = actions_breakdown.get(a.recommended_action, 0) + 1
            total_score += a.composite_score
            risks = json.loads(a.risks_json or "[]")
            if any("Lineage Dependency" in r for r in risks):
                blocked_dependencies += 1
            if any("no assigned owner" in r for r in risks):
                unowned += 1
            if a.composite_score >= 60.0 and len(risks) > 0:
                high_value_risks += 1
            if a.recommended_action in (LifecycleAction.CONSOLIDATE.value, LifecycleAction.RETIRE_CANDIDATE.value):
                rationalization_opps += 1

        avg_score = round(total_score / len(assessments), 1) if assessments else 0.0

        return LifecycleSummaryOut(
            total_assets_assessed=len(assessments),
            actions_breakdown=actions_breakdown,
            avg_composite_score=avg_score,
            assets_blocked_by_dependencies=blocked_dependencies,
            unowned_assets=unowned,
            high_value_governance_risks=high_value_risks,
            rationalization_opportunities=rationalization_opps,
            latest_run_id=latest_run.run_id,
            completed_at=latest_run.completed_at,
        )

    def get_migration_summary(self, db: Session) -> MigrationSummaryOut:
        """Portfolio-level summary of Tableau migration rationalisation."""
        latest_run = (
            db.query(LifecycleEvaluationRuns)
            .filter(LifecycleEvaluationRuns.status == "success")
            .order_by(LifecycleEvaluationRuns.completed_at.desc())
            .first()
        )

        if not latest_run:
            self.evaluate_all(db)
            latest_run = (
                db.query(LifecycleEvaluationRuns)
                .filter(LifecycleEvaluationRuns.status == "success")
                .order_by(LifecycleEvaluationRuns.completed_at.desc())
                .first()
            )

        migrations = (
            db.query(MigrationAssessments)
            .filter(MigrationAssessments.run_id == latest_run.run_id)
            .all()
        )

        actions_breakdown: Dict[str, int] = {}
        complexity_breakdown: Dict[str, int] = {}
        target_models = set()

        for m in migrations:
            actions_breakdown[m.recommended_action] = actions_breakdown.get(m.recommended_action, 0) + 1
            complexity_breakdown[m.technical_complexity] = complexity_breakdown.get(m.technical_complexity, 0) + 1
            if m.candidate_target_model_id:
                target_models.add(m.candidate_target_model_id)

        direct_migrate = actions_breakdown.get(MigrationAction.MIGRATE.value, 0)
        retire_instead = actions_breakdown.get(MigrationAction.RETIRE_INSTEAD_OF_MIGRATE.value, 0)
        consolidate = actions_breakdown.get(MigrationAction.CONSOLIDATE_BEFORE_MIGRATION.value, 0)
        fix_before = actions_breakdown.get(MigrationAction.FIX_BEFORE_MIGRATION.value, 0)
        hold_review = actions_breakdown.get(MigrationAction.HOLD_FOR_REVIEW.value, 0)

        # Effort reduction: avoided migrations (retire + consolidate) / total
        avoided_count = retire_instead + consolidate
        effort_reduction_pct = round((avoided_count / len(migrations)) * 100.0, 1) if migrations else 0.0

        return MigrationSummaryOut(
            total_tableau_assets=len(migrations),
            actions_breakdown=actions_breakdown,
            complexity_breakdown=complexity_breakdown,
            direct_migrate_count=direct_migrate,
            consolidate_count=consolidate,
            retire_instead_count=retire_instead,
            fix_before_migrate_count=fix_before,
            hold_review_count=hold_review,
            estimated_effort_reduction_pct=effort_reduction_pct,
            candidate_target_models=sorted(list(target_models)),
        )


lifecycle_engine = LifecycleEngine()
