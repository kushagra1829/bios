from typing import List, Optional, Dict, Any, Set
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
from backend.app.models.core import SemanticModels, AnalyticsAssets, LineageEdges
from backend.app.models.governance import MigrationBacklog


class LineageRequiredRule(BaseGovernanceRule):
    """
    RULE-004 — Lineage required.
    Operational requirement: Recommendations affecting important pharma reports
    should show upstream models and downstream impact.
    Detects orphan models with no lineage graph presence (e.g. SM-009), and flags
    assets targeted for lifecycle action (e.g. RETIRE / CONSOLIDATE) that have
    unmitigated downstream dependent assets.
    """

    rule_id = RuleId.RULE_004
    rule_name = "Lineage required"
    rule_description = "Recommendations affecting important pharma reports should show upstream models and downstream impact."
    priority = "high"
    category = "lineage_integrity"
    target_entities = ["model", "asset"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Detect Orphan Semantic Models with zero lineage presence
        all_models = db.query(SemanticModels).all()
        lineage_sources: Set[str] = {r[0] for r in db.query(LineageEdges.source_id).all()}
        lineage_targets: Set[str] = {r[0] for r in db.query(LineageEdges.target_id).all()}
        all_lineage_nodes = lineage_sources | lineage_targets

        for model in all_models:
            if model.model_id not in all_lineage_nodes:
                ref = create_evidence_reference(
                    source_table="semantic_models",
                    record_id=model.model_id,
                    field_name="model_id",
                    observed_value=model.model_id,
                    expected_condition="Must have recorded upstream or downstream edges in lineage_edges",
                    metadata={
                        "model_name": model.model_name,
                        "product_scope": model.product_scope,
                        "region_scope": model.region_scope,
                    },
                )

                bundle = create_evidence_bundle(
                    primary_reference=ref,
                    context_notes=f"Semantic model {model.model_id} has 0 edges in the lineage graph.",
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.MODEL,
                        target_entity_id=model.model_id,
                        category=self.category,
                        severity=FindingSeverity.HIGH,
                        status=FindingStatus.OPEN,
                        title=f"Orphan semantic model {model.model_id} missing lineage edges",
                        explanation=(
                            f"Semantic model {model.model_id} ('{model.model_name}') has no registered "
                            "upstream or downstream dependencies in lineage_edges. Without lineage mapping, "
                            "downstream impact of schema modifications cannot be calculated."
                        ),
                        observed_value="0 lineage edges",
                        expected_condition="Mapped upstream source and downstream consumer edges",
                        recommended_action=(
                            f"Register complete lineage edges for {model.model_id} before deploying "
                            "any downstream analytics."
                        ),
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        # 2. Detect Lifecycle/Migration Candidates with Unmitigated Downstream Asset Dependents
        downstream_edges = (
            db.query(LineageEdges)
            .filter(LineageEdges.edge_type == "ASSET_TO_ASSET")
            .all()
        )
        source_to_dependents: Dict[str, List[str]] = {}
        for edge in downstream_edges:
            source_to_dependents.setdefault(edge.source_id, []).append(edge.target_id)

        backlog_items = db.query(MigrationBacklog).all()
        for item in backlog_items:
            if item.source_asset_id in source_to_dependents:
                dependents = source_to_dependents[item.source_asset_id]
                asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == item.source_asset_id).first()
                asset_name = asset.asset_name if asset else item.source_asset_id

                primary_ref = create_evidence_reference(
                    source_table="migration_backlog",
                    record_id=item.source_asset_id,
                    field_name="recommended_path_candidate",
                    observed_value=item.recommended_path_candidate,
                    expected_condition="Zero unmitigated downstream asset dependencies before lifecycle transition",
                    metadata={"dependents": dependents, "status": item.status},
                )

                corroborating = [
                    create_evidence_reference(
                        source_table="lineage_edges",
                        record_id=f"{item.source_asset_id}:{dep_id}",
                        field_name="target_id",
                        observed_value=dep_id,
                        expected_condition="Downstream dependent must be rerouted or decommissioned first",
                    )
                    for dep_id in dependents[:3]
                ]

                bundle = create_evidence_bundle(
                    primary_reference=primary_ref,
                    corroborating_references=corroborating,
                    context_notes=(
                        f"Asset {item.source_asset_id} has {len(dependents)} downstream dependent "
                        f"asset(s): {', '.join(dependents)}."
                    ),
                )

                severity = (
                    FindingSeverity.CRITICAL
                    if item.recommended_path_candidate == "RETIRE"
                    else FindingSeverity.HIGH
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.ASSET,
                        target_entity_id=item.source_asset_id,
                        category=self.category,
                        severity=severity,
                        status=FindingStatus.OPEN,
                        title=f"Unmitigated downstream lineage: {item.source_asset_id} ({item.recommended_path_candidate})",
                        explanation=(
                            f"Asset {item.source_asset_id} ('{asset_name}') is queued for "
                            f"'{item.recommended_path_candidate}', but {len(dependents)} downstream asset(s) "
                            f"depend on it ({', '.join(dependents)}). Executing lifecycle actions without "
                            "re-pointing downstream lineage will break dependent reports."
                        ),
                        observed_value=f"{item.recommended_path_candidate} with {len(dependents)} downstream dependent(s)",
                        expected_condition="All downstream lineage dependencies re-routed or decommissioned",
                        recommended_action=(
                            f"Re-point downstream assets ({', '.join(dependents)}) to a certified target "
                            f"model before executing {item.recommended_path_candidate} on {item.source_asset_id}."
                        ),
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        return findings

