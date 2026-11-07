import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.lifecycle.schemas import MigrationAction, MigrationAssessmentOut
from backend.app.models.core import AnalyticsAssets, SemanticModels, AssetUsage, LineageEdges
from backend.app.models.governance import MigrationBacklog, AssetKpiMap, KpiCatalog

logger = logging.getLogger(__name__)


class MigrationIntelligenceEngine:
    """
    Migration intelligence for Tableau-to-Power BI modernization.
    Evaluates the 94 Tableau legacy assets against usage, complexity, target semantic model readiness,
    downstream lineage dependencies, and KPI compatibility.
    Classifies assets into:
      - MIGRATE: Direct migration to target shared semantic model.
      - CONSOLIDATE_BEFORE_MIGRATION: Merge redundant reporting logic before rebuilding.
      - RETIRE_INSTEAD_OF_MIGRATE: Decommission obsolete content with zero downstream dependents.
      - FIX_BEFORE_MIGRATION: Resolve semantic model/KPI defects before deploying reports.
      - HOLD_FOR_REVIEW: Blocked by active downstream dependencies or governance flags.
    Prevents costly 1:1 lift-and-shift of legacy waste.
    """

    def evaluate_tableau_assets(self, db: Session) -> List[Dict[str, Any]]:
        """Evaluate all 94 Tableau legacy assets and determine migration path."""
        tableau_assets = (
            db.query(AnalyticsAssets)
            .filter(AnalyticsAssets.platform == "Tableau")
            .order_by(AnalyticsAssets.asset_id.asc())
            .all()
        )

        results: List[Dict[str, Any]] = []

        for asset in tableau_assets:
            backlog_item = (
                db.query(MigrationBacklog)
                .filter(MigrationBacklog.source_asset_id == asset.asset_id)
                .first()
            )

            # 1. Downstream Lineage Dependencies
            downstream_count = (
                db.query(LineageEdges)
                .filter(LineageEdges.source_id == asset.asset_id, LineageEdges.edge_type == "ASSET_TO_ASSET")
                .count()
            )

            # 2. Usage Telemetry
            usage_stats = (
                db.query(
                    func.avg(AssetUsage.views).label("avg_views"),
                    func.avg(AssetUsage.unique_users).label("avg_users"),
                )
                .filter(AssetUsage.asset_id == asset.asset_id)
                .first()
            )
            avg_views = float(usage_stats.avg_views or 0.0) if usage_stats else 0.0
            avg_users = float(usage_stats.avg_users or 0.0) if usage_stats else 0.0

            # 3. Target Model Assessment
            target_model_id = backlog_item.candidate_target_model_id if backlog_item else asset.model_id
            target_model = (
                db.query(SemanticModels).filter(SemanticModels.model_id == target_model_id).first()
                if target_model_id
                else None
            )

            target_model_readiness = target_model.ai_readiness if target_model else "unknown"
            target_model_refresh = target_model.refresh_status if target_model else "unknown"

            # 4. KPI Compatibility
            kpi_maps = db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset.asset_id).all()
            kpi_ids = [m.kpi_id for m in kpi_maps]
            kpi_compatibility_score = 100.0
            if kpi_ids:
                canonical_approved = (
                    db.query(KpiCatalog)
                    .filter(
                        KpiCatalog.kpi_id.in_(kpi_ids),
                        KpiCatalog.definition_status == "canonical",
                        KpiCatalog.approval_status == "approved",
                    )
                    .count()
                )
                kpi_compatibility_score = round((canonical_approved / len(kpi_ids)) * 100.0, 1)

            # 5. Complexity and Business Value
            complexity = backlog_item.complexity if backlog_item else "medium"
            if asset.estimated_audience >= 500 or avg_views >= 100.0:
                business_value = "high"
            elif asset.estimated_audience >= 200 or avg_views >= 40.0:
                business_value = "medium"
            else:
                business_value = "low"

            # 6. Classification Decision Logic & Hard Safeguards
            blockers: List[str] = []
            warnings: List[str] = []
            rec_action = MigrationAction.MIGRATE
            rationale = ""

            # Check if backlog recommends RETIRE
            backlog_path = backlog_item.recommended_path_candidate if backlog_item else "MIGRATE"

            if backlog_path == "RETIRE":
                # Hard Safeguard: Downstream dependencies VETO retirement
                if downstream_count > 0:
                    rec_action = MigrationAction.HOLD_FOR_REVIEW
                    blockers.append(
                        f"Retirement blocked: {downstream_count} downstream report(s) depend on {asset.asset_id}."
                    )
                    rationale = (
                        f"Backlog tagged {asset.asset_id} for retirement, but {downstream_count} downstream reports "
                        "depend on this asset. Held for review to reroute dependencies before decommissioning."
                    )
                else:
                    rec_action = MigrationAction.RETIRE_INSTEAD_OF_MIGRATE
                    rationale = (
                        f"Legacy Tableau asset {asset.asset_id} ('{asset.asset_name}') has low usage ({avg_views:.1f} views) "
                        "and 0 downstream dependents. Decommission rather than investing migration hours."
                    )

            elif backlog_path == "CONSOLIDATE_BEFORE_MIGRATION" or backlog_path == "REBUILD_ON_SHARED_MODEL":
                rec_action = MigrationAction.CONSOLIDATE_BEFORE_MIGRATION
                rationale = (
                    f"Consolidate {asset.asset_id} into target semantic model {target_model_id} prior to migration. "
                    "Prevents recreating redundant calculated fields in Power BI."
                )

            elif target_model and (target_model_refresh == "failed" or target_model_readiness == "poor"):
                rec_action = MigrationAction.FIX_BEFORE_MIGRATION
                warnings.append(
                    f"Target model {target_model_id} refresh is '{target_model_refresh}' with readiness '{target_model_readiness}'."
                )
                rationale = (
                    f"Target semantic model {target_model_id} has defects (refresh: {target_model_refresh}, "
                    f"readiness: {target_model_readiness}). Repair target model before rebuilding {asset.asset_id}."
                )

            elif backlog_path == "HUMAN_REVIEW" or downstream_count > 2 or business_value == "high":
                if downstream_count > 0:
                    warnings.append(f"High-impact asset with {downstream_count} downstream dependents.")
                rec_action = MigrationAction.HOLD_FOR_REVIEW if backlog_path == "HUMAN_REVIEW" else MigrationAction.MIGRATE
                rationale = (
                    f"Asset {asset.asset_id} requires architectural sign-off due to high business impact "
                    f"({asset.estimated_audience} audience, {downstream_count} dependents)."
                    if rec_action == MigrationAction.HOLD_FOR_REVIEW
                    else f"Migrate {asset.asset_id} directly to Power BI on certified model {target_model_id}."
                )

            else:
                rec_action = MigrationAction.MIGRATE
                rationale = f"Clean migration candidate: rebuild {asset.asset_id} on target semantic model {target_model_id}."

            results.append({
                "source_asset_id": asset.asset_id,
                "source_asset_name": asset.asset_name,
                "recommended_action": rec_action.value,
                "business_value": business_value,
                "technical_complexity": complexity,
                "candidate_target_model_id": target_model_id,
                "semantic_model_readiness": target_model_readiness,
                "kpi_compatibility_score": kpi_compatibility_score,
                "downstream_dependency_count": downstream_count,
                "rationalization_rationale": rationale,
                "blockers": blockers,
                "warnings": warnings,
                "approval_required": True,
            })

        return results


migration_engine = MigrationIntelligenceEngine()

