from typing import List, Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.app.governance.rules.base import BaseGovernanceRule
from backend.app.governance.schemas import (
    RuleId,
    FindingSeverity,
    FindingStatus,
    TargetEntityType,
    GovernanceFindingCreate,
)
from backend.app.governance.evidence import create_evidence_reference, create_evidence_bundle
from backend.app.models.core import AnalyticsAssets, AssetUsage, LineageEdges
from backend.app.models.governance import AssetKpiMap, GovernanceSignals


class ExplainLifecycleActionRule(BaseGovernanceRule):
    """
    RULE-008 — Explain every lifecycle action.
    Operational requirement: AI should cite metadata, usage, KPI, lineage and governance
    evidence behind reuse/consolidate/retire/migrate/new-build recommendations.
    Enforces that every asset queued for retirement or lifecycle change (candidate_retire,
    legacy, or LIFECYCLE_REVIEW signal) must provide full multi-dimensional evidence:
    usage telemetry, downstream lineage dependencies, mapped KPIs, and replacement justification.
    Flags high-usage assets marked for retirement without validated replacement pathways.
    """

    rule_id = RuleId.RULE_008
    rule_name = "Explain every lifecycle action"
    rule_description = "AI should cite metadata, usage, KPI, lineage and governance evidence behind reuse/consolidate/retire/migrate/new-build recommendations."
    priority = "high"
    category = "lifecycle_auditability"
    target_entities = ["asset"]

    USAGE_ALERT_VIEWS_THRESHOLD = 100
    USAGE_ALERT_USERS_THRESHOLD = 50

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Evaluate candidate_retire / legacy assets with significant ongoing business usage
        lifecycle_assets = (
            db.query(AnalyticsAssets)
            .filter(AnalyticsAssets.lifecycle_status.in_(["candidate_retire", "legacy"]))
            .all()
        )

        for asset in lifecycle_assets:
            # Query usage statistics
            usage_stats = (
                db.query(
                    func.avg(AssetUsage.views).label("avg_views"),
                    func.avg(AssetUsage.unique_users).label("avg_users"),
                    func.sum(AssetUsage.exports).label("total_exports"),
                )
                .filter(AssetUsage.asset_id == asset.asset_id)
                .first()
            )

            avg_views = float(usage_stats.avg_views or 0.0)
            avg_users = float(usage_stats.avg_users or 0.0)

            # Check if active usage warrants strict explainability and replacement guardrails
            has_active_audience = (
                avg_views >= self.USAGE_ALERT_VIEWS_THRESHOLD
                or avg_users >= self.USAGE_ALERT_USERS_THRESHOLD
                or asset.estimated_audience >= 200
            )

            if has_active_audience:
                # Query downstream lineage
                downstream_count = (
                    db.query(LineageEdges)
                    .filter(LineageEdges.source_id == asset.asset_id)
                    .count()
                )

                # Query mapped KPIs
                kpi_count = (
                    db.query(AssetKpiMap)
                    .filter(AssetKpiMap.asset_id == asset.asset_id)
                    .count()
                )

                primary_ref = create_evidence_reference(
                    source_table="analytics_assets",
                    record_id=asset.asset_id,
                    field_name="lifecycle_status",
                    observed_value=asset.lifecycle_status,
                    expected_condition="Decommissioning requires verified zero-usage or certified replacement",
                    metadata={
                        "asset_name": asset.asset_name,
                        "avg_monthly_views": round(avg_views, 1),
                        "avg_monthly_users": round(avg_users, 1),
                        "estimated_audience": asset.estimated_audience,
                    },
                )

                corroborating = [
                    create_evidence_reference(
                        source_table="asset_usage",
                        record_id=asset.asset_id,
                        field_name="views,unique_users",
                        observed_value=f"views: {avg_views:.1f}, users: {avg_users:.1f}",
                        expected_condition="Usage must be near zero before unassisted retirement",
                    ),
                    create_evidence_reference(
                        source_table="lineage_edges",
                        record_id=asset.asset_id,
                        field_name="downstream_dependents",
                        observed_value=downstream_count,
                        expected_condition="Zero downstream dependencies before decommissioning",
                    ),
                    create_evidence_reference(
                        source_table="asset_kpi_map",
                        record_id=asset.asset_id,
                        field_name="mapped_kpis",
                        observed_value=kpi_count,
                        expected_condition="Mapped metrics reconciled to replacement asset",
                    ),
                ]

                bundle = create_evidence_bundle(
                    primary_reference=primary_ref,
                    corroborating_references=corroborating,
                    context_notes=(
                        f"Asset {asset.asset_id} has {avg_users:.1f} avg monthly users, "
                        f"{avg_views:.1f} avg views, {downstream_count} downstream dependents, "
                        f"and {kpi_count} mapped KPIs."
                    ),
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.ASSET,
                        target_entity_id=asset.asset_id,
                        category=self.category,
                        severity=FindingSeverity.HIGH if avg_users >= 100 else FindingSeverity.MEDIUM,
                        status=FindingStatus.OPEN,
                        title=f"Unjustified retirement risk: {asset.asset_id} has active usage",
                        explanation=(
                            f"Asset {asset.asset_id} ('{asset.asset_name}') is marked '{asset.lifecycle_status}', "
                            f"yet records active monthly usage ({avg_users:.1f} users, {avg_views:.1f} views), "
                            f"{downstream_count} downstream lineage edge(s), and {kpi_count} KPI mappings. "
                            "RULE-008 requires complete multi-pillar evidence (usage, lineage, KPI replacement) "
                            "and human approval before decommissioning active reports."
                        ),
                        observed_value=f"status: {asset.lifecycle_status}, users: {avg_users:.1f}, views: {avg_views:.1f}",
                        expected_condition="Documented replacement pathway, user migration notice, and human approval",
                        recommended_action=(
                            f"Conduct formal retirement impact assessment for {asset.asset_id}, designate "
                            "successor certified report, and require human executive sign-off."
                        ),
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        return findings

