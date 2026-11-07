from typing import List, Optional, Dict, Any
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
from backend.app.models.core import AnalyticsAssets, SemanticModels, Owners


class OwnerRequiredRule(BaseGovernanceRule):
    """
    RULE-003 — Owner required.
    Operational requirement: Production analytics need an accountable owner.
    Enforces that every active or production analytics asset and semantic model
    must have an assigned, active owner. Flags unowned assets (NULL owner) as CRITICAL
    and assets with inactive/departed owners as HIGH.
    """

    rule_id = RuleId.RULE_003
    rule_name = "Owner required"
    rule_description = "Production analytics need an accountable owner."
    priority = "high"
    category = "accountability"
    target_entities = ["asset", "model"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Unowned Analytics Assets (owner_id is NULL)
        unowned_assets = (
            db.query(AnalyticsAssets)
            .filter(AnalyticsAssets.owner_id.is_(None))
            .all()
        )

        for asset in unowned_assets:
            ref = create_evidence_reference(
                source_table="analytics_assets",
                record_id=asset.asset_id,
                field_name="owner_id",
                observed_value=None,
                expected_condition="owner_id IS NOT NULL",
                metadata={
                    "asset_name": asset.asset_name,
                    "lifecycle_status": asset.lifecycle_status,
                    "platform": asset.platform,
                    "workspace_id": asset.workspace_id,
                },
            )

            bundle = create_evidence_bundle(
                primary_reference=ref,
                context_notes=f"Asset {asset.asset_id} has no assigned owner in production.",
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.ASSET,
                    target_entity_id=asset.asset_id,
                    category=self.category,
                    severity=FindingSeverity.CRITICAL,
                    status=FindingStatus.OPEN,
                    title=f"Missing accountable owner on asset {asset.asset_id}",
                    explanation=(
                        f"Asset {asset.asset_id} ('{asset.asset_name}') in workspace "
                        f"{asset.workspace_id} has no accountable owner assigned (owner_id is NULL). "
                        "Unowned assets cannot be certified, audited, or safely modified."
                    ),
                    observed_value="NULL (unowned)",
                    expected_condition="Active accountable owner assigned",
                    recommended_action=(
                        f"Assign an active business or technical owner to asset {asset.asset_id} "
                        "before further operational usage."
                    ),
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        # 2. Assets with Inactive Owners
        inactive_owner_assets = (
            db.query(AnalyticsAssets, Owners)
            .join(Owners, AnalyticsAssets.owner_id == Owners.owner_id)
            .filter(Owners.status == "inactive")
            .all()
        )

        for asset, owner in inactive_owner_assets:
            ref = create_evidence_reference(
                source_table="analytics_assets",
                record_id=asset.asset_id,
                field_name="owner_id",
                observed_value=asset.owner_id,
                expected_condition="Assigned owner must have active status",
                metadata={"asset_name": asset.asset_name, "owner_name": owner.owner_name},
            )

            corroborating = [
                create_evidence_reference(
                    source_table="owners",
                    record_id=owner.owner_id,
                    field_name="status",
                    observed_value=owner.status,
                    expected_condition="active",
                    metadata={"owner_email": owner.email, "role": owner.role},
                )
            ]

            bundle = create_evidence_bundle(
                primary_reference=ref,
                corroborating_references=corroborating,
                context_notes=f"Assigned owner {owner.owner_id} ({owner.owner_name}) is inactive.",
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.ASSET,
                    target_entity_id=asset.asset_id,
                    category=self.category,
                    severity=FindingSeverity.HIGH,
                    status=FindingStatus.OPEN,
                    title=f"Assigned owner inactive on asset {asset.asset_id}",
                    explanation=(
                        f"Asset {asset.asset_id} ('{asset.asset_name}') is assigned to "
                        f"owner {owner.owner_id} ('{owner.owner_name}'), but this owner's status is "
                        f"'{owner.status}'. Inactive ownership impairs incident escalation and governance."
                    ),
                    observed_value=f"{owner.owner_id} (inactive)",
                    expected_condition="Active owner assigned",
                    recommended_action=(
                        f"Reassign asset {asset.asset_id} to an active team lead or business custodian."
                    ),
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        # 3. Semantic Models with Missing or Inactive Owners
        models_inactive_owner = (
            db.query(SemanticModels, Owners)
            .join(Owners, SemanticModels.owner_id == Owners.owner_id)
            .filter(Owners.status == "inactive")
            .all()
        )

        for model, owner in models_inactive_owner:
            ref = create_evidence_reference(
                source_table="semantic_models",
                record_id=model.model_id,
                field_name="owner_id",
                observed_value=model.owner_id,
                expected_condition="Active owner assigned to semantic model",
                metadata={"model_name": model.model_name, "owner_name": owner.owner_name},
            )

            bundle = create_evidence_bundle(
                primary_reference=ref,
                corroborating_references=[
                    create_evidence_reference(
                        source_table="owners",
                        record_id=owner.owner_id,
                        field_name="status",
                        observed_value=owner.status,
                        expected_condition="active",
                    )
                ],
                context_notes=f"Model owner {owner.owner_id} is inactive.",
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.MODEL,
                    target_entity_id=model.model_id,
                    category=self.category,
                    severity=FindingSeverity.HIGH,
                    status=FindingStatus.OPEN,
                    title=f"Assigned owner inactive on semantic model {model.model_id}",
                    explanation=(
                        f"Semantic model {model.model_id} ('{model.model_name}') is assigned to "
                        f"inactive owner {owner.owner_id} ('{owner.owner_name}')."
                    ),
                    observed_value=f"{owner.owner_id} (inactive)",
                    expected_condition="Active model custodian assigned",
                    recommended_action=f"Reassign semantic model {model.model_id} to an active data engineer.",
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        return findings

