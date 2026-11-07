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
from backend.app.models.governance import MigrationBacklog
from backend.app.models.core import AnalyticsAssets, AssetUsage


class DoNotMigrateWasteRule(BaseGovernanceRule):
    """
    RULE-006 — Do not migrate waste.
    Operational requirement: Legacy Tableau assets should be rationalised before
    migration; duplicate low-use content should not be recreated 1:1.
    Flags migration backlog items identified for retirement or pre-consolidation,
    and flags legacy Tableau assets with negligible usage to prevent costly, wasteful 1:1 lift-and-shift.
    """

    rule_id = RuleId.RULE_006
    rule_name = "Do not migrate waste"
    rule_description = "Legacy Tableau assets should be rationalised before migration; duplicate low-use content should not be recreated 1:1."
    priority = "high"
    category = "migration_rationalisation"
    target_entities = ["asset"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Evaluate Migration Backlog candidates tagged for RETIRE or CONSOLIDATE_BEFORE_MIGRATION
        waste_candidates = (
            db.query(MigrationBacklog, AnalyticsAssets)
            .join(AnalyticsAssets, MigrationBacklog.source_asset_id == AnalyticsAssets.asset_id)
            .filter(MigrationBacklog.recommended_path_candidate.in_(["RETIRE", "CONSOLIDATE_BEFORE_MIGRATION"]))
            .all()
        )

        for item, asset in waste_candidates:
            # Query usage statistics to corroborate rationalisation
            avg_views = (
                db.query(func.avg(AssetUsage.views))
                .filter(AssetUsage.asset_id == item.source_asset_id)
                .scalar()
                or 0.0
            )

            primary_ref = create_evidence_reference(
                source_table="migration_backlog",
                record_id=item.source_asset_id,
                field_name="recommended_path_candidate",
                observed_value=item.recommended_path_candidate,
                expected_condition="Decommission or consolidate before initiating migration pipeline",
                metadata={
                    "complexity": item.complexity,
                    "target_model_id": item.candidate_target_model_id,
                    "reason": item.synthetic_reason,
                    "avg_views": round(float(avg_views), 1),
                },
            )

            corroborating = [
                create_evidence_reference(
                    source_table="analytics_assets",
                    record_id=asset.asset_id,
                    field_name="lifecycle_status,platform",
                    observed_value=f"{asset.platform} / {asset.lifecycle_status}",
                    expected_condition="Legacy source platform candidate for rationalisation",
                    metadata={"asset_name": asset.asset_name, "audience": asset.estimated_audience},
                )
            ]

            bundle = create_evidence_bundle(
                primary_reference=primary_ref,
                corroborating_references=corroborating,
                context_notes=(
                    f"Asset {item.source_asset_id} recommended path is '{item.recommended_path_candidate}' "
                    f"due to '{item.synthetic_reason}' (avg monthly views: {avg_views:.1f})."
                ),
            )

            is_retire = item.recommended_path_candidate == "RETIRE"
            rec_action = (
                f"Decommission legacy asset {item.source_asset_id} and archive historical queries without migrating."
                if is_retire
                else f"Consolidate {item.source_asset_id} into target semantic model {item.candidate_target_model_id} rather than 1:1 rebuild."
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.ASSET,
                    target_entity_id=item.source_asset_id,
                    category=self.category,
                    severity=FindingSeverity.HIGH if is_retire else FindingSeverity.MEDIUM,
                    status=FindingStatus.OPEN,
                    title=f"Waste rationalisation: {item.source_asset_id} ({item.recommended_path_candidate})",
                    explanation=(
                        f"Legacy asset {item.source_asset_id} ('{asset.asset_name}') is flagged as "
                        f"'{item.recommended_path_candidate}' ({item.synthetic_reason}). "
                        "Recreating redundant, legacy, or low-use assets 1:1 on Power BI / Fabric "
                        "perpetuates technical debt and increases migration overhead."
                    ),
                    observed_value=f"Path: {item.recommended_path_candidate}, reason: {item.synthetic_reason}",
                    expected_condition="Rationalised or retired prior to migration pipeline execution",
                    recommended_action=rec_action,
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        return findings

