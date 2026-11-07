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
from backend.app.models.core import AnalyticsAssets
from backend.app.models.governance import GovernanceSignals


class HighReachRequiresTrustRule(BaseGovernanceRule):
    """
    RULE-005 — High reach requires trust.
    Operational requirement: High-audience content should be certified/promoted or reviewed.
    Ensures analytics consumed by wide business audiences (>500 users) undergo formal
    endorsement and review, and flags self-service reports with high reach (>250 users)
    operating without certification.
    """

    rule_id = RuleId.RULE_005
    rule_name = "High reach requires trust"
    rule_description = "High-audience content should be certified/promoted or reviewed."
    priority = "medium"
    category = "trust_endorsement"
    target_entities = ["asset"]

    AUDIENCE_THRESHOLD_HIGH = 500
    AUDIENCE_THRESHOLD_SELF_SERVICE = 250

    def get_thresholds(self) -> Dict[str, Any]:
        return {
            "audience_threshold_high": self.AUDIENCE_THRESHOLD_HIGH,
            "audience_threshold_self_service": self.AUDIENCE_THRESHOLD_SELF_SERVICE,
        }

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # Pre-fetch existing signals for corroboration
        existing_signals = {
            s.asset_id: s.signal_code
            for s in db.query(GovernanceSignals)
            .filter(GovernanceSignals.signal_code.in_(["HIGH_REACH_UNENDORSED", "SELF_SERVICE_HIGH_REACH"]))
            .all()
        }

        # 1. High-audience assets (>500) with endorsement == 'none'
        high_reach_unendorsed = (
            db.query(AnalyticsAssets)
            .filter(
                AnalyticsAssets.estimated_audience >= self.AUDIENCE_THRESHOLD_HIGH,
                AnalyticsAssets.endorsement == "none",
            )
            .all()
        )

        for asset in high_reach_unendorsed:
            ref = create_evidence_reference(
                source_table="analytics_assets",
                record_id=asset.asset_id,
                field_name="estimated_audience,endorsement",
                observed_value=f"audience: {asset.estimated_audience}, endorsement: {asset.endorsement}",
                expected_condition=f"estimated_audience >= {self.AUDIENCE_THRESHOLD_HIGH} requires endorsement IN ('certified', 'promoted')",
                metadata={
                    "asset_name": asset.asset_name,
                    "estimated_audience": asset.estimated_audience,
                    "platform": asset.platform,
                    "delivery_model": asset.delivery_model,
                },
            )

            corroborating = []
            if asset.asset_id in existing_signals:
                corroborating.append(
                    create_evidence_reference(
                        source_table="governance_signals",
                        record_id=asset.asset_id,
                        field_name="signal_code",
                        observed_value=existing_signals[asset.asset_id],
                        expected_condition="Corroborated by historical governance telemetry",
                    )
                )

            bundle = create_evidence_bundle(
                primary_reference=ref,
                corroborating_references=corroborating,
                context_notes=(
                    f"Asset {asset.asset_id} reaches {asset.estimated_audience} users without endorsement."
                ),
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.ASSET,
                    target_entity_id=asset.asset_id,
                    category=self.category,
                    severity=FindingSeverity.HIGH if asset.estimated_audience >= 1000 else FindingSeverity.MEDIUM,
                    status=FindingStatus.OPEN,
                    title=f"Unendorsed high-reach asset {asset.asset_id} (audience: {asset.estimated_audience})",
                    explanation=(
                        f"Asset {asset.asset_id} ('{asset.asset_name}') has an estimated audience of "
                        f"{asset.estimated_audience} users but has no endorsement ('{asset.endorsement}'). "
                        "High-reach decision-making assets must be certified or formally promoted to ensure "
                        "data consistency and trust."
                    ),
                    observed_value=f"{asset.estimated_audience} users, endorsement: '{asset.endorsement}'",
                    expected_condition="Certified or promoted endorsement status",
                    recommended_action=(
                        f"Initiate formal certification review for {asset.asset_id} or restrict workspace distribution."
                    ),
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        # 2. Self-service assets with high audience (>=250) lacking certification
        self_service_candidates = (
            db.query(AnalyticsAssets)
            .filter(
                AnalyticsAssets.delivery_model == "self_service",
                AnalyticsAssets.estimated_audience >= self.AUDIENCE_THRESHOLD_SELF_SERVICE,
                AnalyticsAssets.endorsement == "none",
                # Don't double flag if already flagged above
                AnalyticsAssets.estimated_audience < self.AUDIENCE_THRESHOLD_HIGH,
            )
            .all()
        )

        for asset in self_service_candidates:
            ref = create_evidence_reference(
                source_table="analytics_assets",
                record_id=asset.asset_id,
                field_name="delivery_model,estimated_audience",
                observed_value=f"delivery: self_service, audience: {asset.estimated_audience}",
                expected_condition="Self-service assets with audience >= 250 must undergo BI governance review",
                metadata={"asset_name": asset.asset_name},
            )

            bundle = create_evidence_bundle(
                primary_reference=ref,
                context_notes=f"Self-service asset reaches {asset.estimated_audience} users without formal review.",
            )

            findings.append(
                GovernanceFindingCreate(
                    rule_id=self.rule_id,
                    target_entity_type=TargetEntityType.ASSET,
                    target_entity_id=asset.asset_id,
                    category=self.category,
                    severity=FindingSeverity.MEDIUM,
                    status=FindingStatus.OPEN,
                    title=f"Unreviewed self-service reach: {asset.asset_id} (audience: {asset.estimated_audience})",
                    explanation=(
                        f"Self-service asset {asset.asset_id} ('{asset.asset_name}') reaches "
                        f"{asset.estimated_audience} users without central BI validation. "
                        "Unvetted self-service reports with wide distribution present regulatory and metric risk."
                    ),
                    observed_value=f"self_service delivery with {asset.estimated_audience} audience",
                    expected_condition="Central BI review or promotion before scaling audience",
                    recommended_action=(
                        f"Review self-service asset {asset.asset_id} for migration to managed central BI delivery."
                    ),
                    human_approval_required=True,
                    evidence_bundle=bundle,
                )
            )

        return findings

