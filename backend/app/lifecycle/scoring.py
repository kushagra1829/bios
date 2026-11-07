import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.lifecycle.schemas import LifecycleScoreBreakdown
from backend.app.models.core import AnalyticsAssets, SemanticModels, AssetUsage, LineageEdges, Owners
from backend.app.models.governance import AssetKpiMap, KpiCatalog

logger = logging.getLogger(__name__)


class LifecycleScoringEngine:
    """
    Deterministic lifecycle scoring model for BIOS.
    Published Formula:
      S_composite = 0.25 * S_usage
                  + 0.20 * S_reach
                  + 0.20 * S_gov
                  + 0.15 * S_lineage
                  + 0.10 * S_kpi
                  + 0.10 * S_semantic
    All sub-scores are normalized to [0.0, 100.0].
    """

    WEIGHT_USAGE = 0.25
    WEIGHT_REACH = 0.20
    WEIGHT_GOVERNANCE = 0.20
    WEIGHT_LINEAGE = 0.15
    WEIGHT_KPI = 0.10
    WEIGHT_SEMANTIC = 0.10

    def calculate_score(
        self,
        asset: AnalyticsAssets,
        db: Session,
        downstream_dependents_count: Optional[int] = None,
    ) -> tuple[LifecycleScoreBreakdown, Dict[str, Any]]:
        """Compute the multi-factor lifecycle score and collect raw evidence metrics."""
        evidence: Dict[str, Any] = {"asset_id": asset.asset_id}

        # 1. Usage Component (25%)
        usage_stats = (
            db.query(
                func.avg(AssetUsage.views).label("avg_views"),
                func.avg(AssetUsage.unique_users).label("avg_users"),
                func.sum(AssetUsage.query_errors).label("total_errors"),
                func.count(AssetUsage.month).label("month_count"),
            )
            .filter(AssetUsage.asset_id == asset.asset_id)
            .first()
        )

        avg_views = float(usage_stats.avg_views or 0.0) if usage_stats else 0.0
        avg_users = float(usage_stats.avg_users or 0.0) if usage_stats else 0.0
        total_errors = int(usage_stats.total_errors or 0) if usage_stats else 0
        month_count = int(usage_stats.month_count or 0) if usage_stats else 0

        views_ratio = min(100.0, (avg_views / 250.0) * 100.0)
        users_ratio = min(100.0, (avg_users / 50.0) * 100.0)
        error_penalty = min(20.0, total_errors * 2.0)
        usage_score = max(0.0, min(100.0, (0.6 * views_ratio + 0.4 * users_ratio) - error_penalty))

        evidence["usage"] = {
            "avg_views": round(avg_views, 1),
            "avg_users": round(avg_users, 1),
            "months_recorded": month_count,
            "total_errors": total_errors,
        }

        # 2. Audience & Criticality Component (20%)
        audience = asset.estimated_audience or 0
        audience_base = min(80.0, (audience / 1500.0) * 80.0)

        # Check KPI criticality
        kpi_maps = db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset.asset_id).all()
        kpi_ids = [m.kpi_id for m in kpi_maps]
        has_critical_kpi = False
        if kpi_ids:
            crit_count = (
                db.query(KpiCatalog)
                .filter(KpiCatalog.kpi_id.in_(kpi_ids), KpiCatalog.business_criticality.in_(["critical", "high"]))
                .count()
            )
            has_critical_kpi = crit_count > 0

        crit_boost = 20.0 if (has_critical_kpi or asset.classification == "confidential") else 0.0
        audience_reach_score = min(100.0, audience_base + crit_boost)

        evidence["reach"] = {
            "estimated_audience": audience,
            "classification": asset.classification,
            "has_critical_kpi": has_critical_kpi,
        }

        # 3. Governance Trust Component (20%)
        endorsement_score = 100.0 if asset.endorsement == "certified" else (75.0 if asset.endorsement == "promoted" else 25.0)

        owner_score = 0.0
        owner_name = "Unassigned"
        owner_status = "missing"
        if asset.owner_id:
            owner = db.query(Owners).filter(Owners.owner_id == asset.owner_id).first()
            if owner:
                owner_name = owner.owner_name
                owner_status = owner.status
                owner_score = 100.0 if owner.status == "active" else 30.0

        governance_trust_score = round(0.5 * endorsement_score + 0.5 * owner_score, 1)

        evidence["governance"] = {
            "endorsement": asset.endorsement,
            "owner_id": asset.owner_id,
            "owner_name": owner_name,
            "owner_status": owner_status,
        }

        # 4. Lineage & Dependency Component (15%)
        if downstream_dependents_count is None:
            downstream_dependents_count = (
                db.query(LineageEdges)
                .filter(LineageEdges.source_id == asset.asset_id, LineageEdges.edge_type == "ASSET_TO_ASSET")
                .count()
            )

        if downstream_dependents_count > 0:
            lineage_dependency_score = min(100.0, 50.0 + (downstream_dependents_count * 25.0))
        else:
            # Check upstream model edge
            has_upstream = (
                db.query(LineageEdges)
                .filter(LineageEdges.target_id == asset.asset_id, LineageEdges.edge_type == "MODEL_TO_ASSET")
                .count()
                > 0
            )
            lineage_dependency_score = 50.0 if has_upstream else 20.0

        evidence["lineage"] = {
            "downstream_dependent_count": downstream_dependents_count,
            "has_upstream_model_edge": (lineage_dependency_score >= 50.0),
        }

        # 5. KPI Quality Component (10%)
        if kpi_ids:
            canonical_approved_cnt = (
                db.query(KpiCatalog)
                .filter(
                    KpiCatalog.kpi_id.in_(kpi_ids),
                    KpiCatalog.definition_status == "canonical",
                    KpiCatalog.approval_status == "approved",
                )
                .count()
            )
            kpi_quality_score = round((canonical_approved_cnt / len(kpi_ids)) * 100.0, 1)
        else:
            kpi_quality_score = 50.0  # neutral if no mapped KPIs
            canonical_approved_cnt = 0

        evidence["kpi"] = {
            "mapped_kpi_count": len(kpi_ids),
            "canonical_approved_count": canonical_approved_cnt,
        }

        # 6. Semantic Model Health Component (10%)
        model = db.query(SemanticModels).filter(SemanticModels.model_id == asset.model_id).first() if asset.model_id else None
        if model:
            readiness_pts = 100.0 if model.ai_readiness == "good" else (60.0 if model.ai_readiness == "partial" else 20.0)
            refresh_pts = 100.0 if model.refresh_status == "healthy" else (50.0 if model.refresh_status == "warning" else 0.0)
            semantic_health_score = round(0.5 * readiness_pts + 0.5 * refresh_pts, 1)
            evidence["semantic_model"] = {
                "model_id": model.model_id,
                "model_name": model.model_name,
                "ai_readiness": model.ai_readiness,
                "refresh_status": model.refresh_status,
            }
        else:
            semantic_health_score = 30.0
            evidence["semantic_model"] = None

        # Composite Score
        composite_score = round(
            (self.WEIGHT_USAGE * usage_score)
            + (self.WEIGHT_REACH * audience_reach_score)
            + (self.WEIGHT_GOVERNANCE * governance_trust_score)
            + (self.WEIGHT_LINEAGE * lineage_dependency_score)
            + (self.WEIGHT_KPI * kpi_quality_score)
            + (self.WEIGHT_SEMANTIC * semantic_health_score),
            1,
        )

        breakdown = LifecycleScoreBreakdown(
            usage_score=round(usage_score, 1),
            audience_reach_score=round(audience_reach_score, 1),
            governance_trust_score=round(governance_trust_score, 1),
            lineage_dependency_score=round(lineage_dependency_score, 1),
            kpi_quality_score=round(kpi_quality_score, 1),
            semantic_health_score=round(semantic_health_score, 1),
            composite_score=composite_score,
        )

        return breakdown, evidence


scoring_engine = LifecycleScoringEngine()

