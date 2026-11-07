import logging
from typing import List, Dict, Any, Tuple
from backend.app.lifecycle.schemas import LifecycleAction, LifecycleScoreBreakdown
from backend.app.models.core import AnalyticsAssets

logger = logging.getLogger(__name__)


class LifecycleRulesEngine:
    """
    Evaluates scoring breakdowns against non-negotiable governance safeguards.
    Determines the authoritative LifecycleAction (KEEP, IMPROVE, CONSOLIDATE, REVIEW, RETIRE_CANDIDATE, MIGRATE).
    Enforces hard veto rules:
      - VETO 1: Downstream dependents strictly veto retirement.
      - VETO 2: Certified/promoted endorsement strictly vetoes casual retirement.
      - VETO 3: Low usage alone never justifies unassisted retirement.
      - VETO 4: Insufficient usage evidence forces REVIEW.
      - VETO 5: Tableau platform assets are routed to migration intelligence.
    """

    def evaluate_asset(
        self,
        asset: AnalyticsAssets,
        score: LifecycleScoreBreakdown,
        evidence: Dict[str, Any],
    ) -> Tuple[LifecycleAction, float, str, List[str], bool]:
        """
        Returns:
          (LifecycleAction, confidence, explanation, risks_and_dependencies, approval_required)
        """
        risks: List[str] = []
        downstream_count = evidence.get("lineage", {}).get("downstream_dependent_count", 0)
        has_critical_kpi = evidence.get("reach", {}).get("has_critical_kpi", False)
        is_endorsed = asset.endorsement in ("certified", "promoted")
        is_unowned = asset.owner_id is None
        usage_info = evidence.get("usage", {})
        months_recorded = usage_info.get("months_recorded", 0)
        avg_views = usage_info.get("avg_views", 0.0)

        # 1. Platform Check: Tableau assets belong in Migration Assessment
        if asset.platform == "Tableau":
            return (
                LifecycleAction.MIGRATE,
                0.90,
                f"Asset {asset.asset_id} is on legacy platform Tableau. Rationalisation and migration pipeline applies.",
                ["Legacy platform migration required."],
                True,
            )

        # 2. Hard Safeguard: Insufficient Evidence Check
        if months_recorded == 0:
            return (
                LifecycleAction.REVIEW,
                0.50,
                f"Asset {asset.asset_id} lacks recorded usage telemetry. Insufficient evidence forces a governance review.",
                ["Missing telemetry prevents automated lifecycle scoring."],
                True,
            )

        # 3. Ownership Defect Warning
        if is_unowned:
            risks.append("Asset has no assigned owner. Governance remediation required.")

        # 4. Downstream Dependency Checks
        if downstream_count > 0:
            risks.append(f"Lineage Dependency Anchor: {downstream_count} downstream reports depend on this asset.")

        # 5. Semantic Model Health Check
        sem_info = evidence.get("semantic_model")
        if sem_info and sem_info.get("refresh_status") in ("failed", "warning"):
            risks.append(f"ETL Refresh Risk: Model {sem_info.get('model_id')} refresh status is '{sem_info.get('refresh_status')}'.")

        # 6. Evaluation Logic & Hard Vetoes

        # Rule A: RETIRE_CANDIDATE
        # Criteria: Low composite score (< 40) OR explicit candidate_retire status,
        # BUT MUST PASS ALL HARD VETOES:
        #  - Veto 1: No downstream dependents (downstream_count == 0)
        #  - Veto 2: Not certified or promoted
        #  - Veto 3: Not high criticality
        #  - Veto 4: Low usage (avg_views < 50)
        is_candidate_for_retire = (
            score.composite_score < 42.0
            or asset.lifecycle_status == "candidate_retire"
            or (avg_views < 15.0 and not is_endorsed)
        )

        if is_candidate_for_retire:
            # Check Veto 1: Downstream Dependents
            if downstream_count > 0:
                return (
                    LifecycleAction.REVIEW,
                    0.88,
                    f"Retirement VETOED: Asset {asset.asset_id} has {downstream_count} downstream dependent report(s). "
                    "In accordance with Lineage Safeguards, assets with active consumers cannot be retired until dependencies are rerouted.",
                    risks,
                    True,
                )

            # Check Veto 2: Endorsement Protection
            if is_endorsed:
                return (
                    LifecycleAction.REVIEW,
                    0.85,
                    f"Retirement VETOED: Asset {asset.asset_id} holds endorsement '{asset.endorsement}'. "
                    "Endorsed assets cannot be retired automatically; formal BI board decommissioning review required.",
                    risks,
                    True,
                )

            # Check Veto 3: Criticality Protection
            if has_critical_kpi or asset.classification == "confidential":
                return (
                    LifecycleAction.REVIEW,
                    0.82,
                    f"Retirement VETOED: Asset {asset.asset_id} is associated with critical business KPIs. Review required.",
                    risks,
                    True,
                )

            # Check Veto 4: Active Usage
            if avg_views >= 50.0:
                return (
                    LifecycleAction.CONSOLIDATE,
                    0.80,
                    f"Retirement VETOED: Asset {asset.asset_id} is marked '{asset.lifecycle_status}', but retains "
                    f"active monthly usage ({avg_views:.1f} views). Recommended action is consolidation rather than abrupt retirement.",
                    risks,
                    True,
                )

            # All vetoes passed -> Legitimate Retire Candidate
            return (
                LifecycleAction.RETIRE_CANDIDATE,
                0.90,
                f"Asset {asset.asset_id} exhibits low usage ({avg_views:.1f} views), zero downstream dependencies, "
                "and no certified endorsement. Safe candidate for decommissioning following user notification.",
                risks,
                True,
            )

        # Rule B: CONSOLIDATE
        # Criteria: Legacy status with ongoing usage, or low KPI quality (< 50%) but moderate usage
        if asset.lifecycle_status == "legacy" or (score.kpi_quality_score < 40.0 and score.usage_score >= 40.0):
            return (
                LifecycleAction.CONSOLIDATE,
                0.85,
                f"Asset {asset.asset_id} is in '{asset.lifecycle_status}' status with {avg_views:.1f} monthly views. "
                "Consolidate measures into a shared certified semantic model to eliminate reporting debt.",
                risks,
                True,
            )

        # Rule C: IMPROVE
        # Criteria: High value/audience, but governance/semantic flaws (e.g. unowned, poor AI readiness, failed refresh, unapproved KPIs)
        needs_improvement = (
            score.semantic_health_score < 55.0
            or score.kpi_quality_score < 60.0
            or is_unowned
            or (score.audience_reach_score >= 60.0 and asset.endorsement == "none")
        )

        if needs_improvement and score.composite_score >= 45.0:
            reasons = []
            if is_unowned:
                reasons.append("assign active owner")
            if score.semantic_health_score < 55.0:
                reasons.append("repair semantic model / refresh")
            if score.kpi_quality_score < 60.0:
                reasons.append("align with canonical KPIs")
            if asset.endorsement == "none" and score.audience_reach_score >= 60.0:
                reasons.append("promote or certify high-reach content")

            return (
                LifecycleAction.IMPROVE,
                0.86,
                f"Asset {asset.asset_id} delivers high business value (score: {score.composite_score:.1f}), "
                f"but requires governance remediation: {', '.join(reasons)}.",
                risks,
                True,
            )

        # Rule D: KEEP
        # Criteria: Healthy scores across usage, governance, model, and KPIs
        if score.composite_score >= 65.0 and not is_unowned:
            return (
                LifecycleAction.KEEP,
                0.92,
                f"Asset {asset.asset_id} demonstrates high health and business utility (score: {score.composite_score:.1f}). "
                "Maintained as active production analytics.",
                risks,
                False,
            )

        # Rule E: Default REVIEW
        return (
            LifecycleAction.REVIEW,
            0.75,
            f"Asset {asset.asset_id} presents balanced operational indicators (score: {score.composite_score:.1f}). "
            "Bi-annual portfolio review recommended.",
            risks,
            True,
        )


lifecycle_rules = LifecycleRulesEngine()

