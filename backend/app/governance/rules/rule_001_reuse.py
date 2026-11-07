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
from backend.app.models.core import AnalyticsAssets, SemanticModels
from backend.app.models.governance import BusinessRequests


class ReuseBeforeBuildRule(BaseGovernanceRule):
    """
    RULE-001 — Reuse before build.
    Operational requirement: Search existing certified/promoted assets and shared
    semantic models before creating new content. Prohibit redundant report builds
    when reusable certified analytics already cover the domain/scope.
    """

    rule_id = RuleId.RULE_001
    rule_name = "Reuse before build"
    rule_description = "Search existing certified/promoted assets and shared semantic models before creating new content."
    priority = "high"
    category = "waste_reduction"
    target_entities = ["asset", "request"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Evaluate Duplicate Asset Names across estate (proliferation of redundant assets)
        dup_names = (
            db.query(AnalyticsAssets.asset_name, func.count(AnalyticsAssets.asset_id).label("cnt"))
            .group_by(AnalyticsAssets.asset_name)
            .having(func.count(AnalyticsAssets.asset_id) > 1)
            .all()
        )

        dup_name_set = {row[0] for row in dup_names}
        if dup_name_set:
            dup_assets = (
                db.query(AnalyticsAssets)
                .filter(AnalyticsAssets.asset_name.in_(dup_name_set))
                .order_by(AnalyticsAssets.asset_name, AnalyticsAssets.asset_id)
                .all()
            )

            # Group by asset name
            by_name: Dict[str, List[AnalyticsAssets]] = {}
            for a in dup_assets:
                by_name.setdefault(a.asset_name, []).append(a)

            for name, assets in by_name.items():
                # If one is certified/promoted, the others are redundant duplicates
                certified = [a for a in assets if a.endorsement in ("certified", "promoted")]
                for asset in assets:
                    # Flag every asset in the duplicate group with reference to peer duplicates
                    peers = [p.asset_id for p in assets if p.asset_id != asset.asset_id]
                    peer_str = ", ".join(peers)

                    ref = create_evidence_reference(
                        source_table="analytics_assets",
                        record_id=asset.asset_id,
                        field_name="asset_name",
                        observed_value=asset.asset_name,
                        expected_condition="Unique asset title with distinct analytical scope",
                        metadata={"peer_duplicate_asset_ids": peers, "endorsement": asset.endorsement},
                    )

                    corroborating = []
                    if certified and asset not in certified:
                        cert_peers = [c.asset_id for c in certified]
                        corroborating.append(
                            create_evidence_reference(
                                source_table="analytics_assets",
                                record_id=cert_peers[0],
                                field_name="endorsement",
                                observed_value="certified/promoted",
                                expected_condition="Target for consolidation",
                            )
                        )

                    bundle = create_evidence_bundle(
                        primary_reference=ref,
                        corroborating_references=corroborating,
                        context_notes=f"Found {len(assets)} assets sharing identical title '{name}'.",
                    )

                    rec_action = (
                        f"Consolidate {asset.asset_id} into certified asset {certified[0].asset_id}."
                        if certified and asset not in certified
                        else f"Review and deduplicate {asset.asset_id} against duplicates: {peer_str}."
                    )

                    findings.append(
                        GovernanceFindingCreate(
                            rule_id=self.rule_id,
                            target_entity_type=TargetEntityType.ASSET,
                            target_entity_id=asset.asset_id,
                            category=self.category,
                            severity=FindingSeverity.HIGH if (certified and asset not in certified) else FindingSeverity.MEDIUM,
                            status=FindingStatus.OPEN,
                            title=f"Duplicate asset title: '{name}' ({len(assets)} occurrences)",
                            explanation=(
                                f"Asset {asset.asset_id} shares identical title '{name}' with "
                                f"{len(peers)} other assets ({peer_str}). Redundant asset creation "
                                "violates the reuse-before-build governance policy."
                            ),
                            observed_value=f"Title '{name}' shared across {len(assets)} assets",
                            expected_condition="Distinct, non-duplicated asset titles across estate",
                            recommended_action=rec_action,
                            human_approval_required=True,
                            evidence_bundle=bundle,
                        )
                    )

        # 2. Evaluate Inbound Business Requests where certified assets already exist for scope
        requests = db.query(BusinessRequests).all()
        for req in requests:
            matching_certified = (
                db.query(AnalyticsAssets)
                .filter(
                    AnalyticsAssets.product_scope == req.product_context,
                    AnalyticsAssets.market_scope == req.market_context,
                    AnalyticsAssets.endorsement.in_(["certified", "promoted"]),
                )
                .all()
            )

            if matching_certified:
                cert_ids = [c.asset_id for c in matching_certified]
                ref = create_evidence_reference(
                    source_table="business_requests",
                    record_id=req.request_id,
                    field_name="product_context,market_context",
                    observed_value=f"{req.product_context} / {req.market_context}",
                    expected_condition="No existing certified analytics coverage before commissioning new asset",
                    metadata={"matching_certified_assets": cert_ids},
                )
                corroborating = [
                    create_evidence_reference(
                        source_table="analytics_assets",
                        record_id=c.asset_id,
                        field_name="endorsement",
                        observed_value=c.endorsement,
                        expected_condition="Available for reuse",
                        metadata={"asset_name": c.asset_name},
                    )
                    for c in matching_certified[:3]
                ]

                bundle = create_evidence_bundle(
                    primary_reference=ref,
                    corroborating_references=corroborating,
                    context_notes=f"{len(matching_certified)} certified/promoted assets exist for this scope.",
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.REQUEST,
                        target_entity_id=req.request_id,
                        category=self.category,
                        severity=FindingSeverity.HIGH,
                        status=FindingStatus.OPEN,
                        title=f"Reuse candidate found for request {req.request_id} ({req.product_context}/{req.market_context})",
                        explanation=(
                            f"Business request {req.request_id} requests analytics for "
                            f"{req.product_context} in {req.market_context}, but {len(matching_certified)} "
                            f"certified/promoted assets already exist ({', '.join(cert_ids[:3])}). "
                            "Content should be reused rather than commissioned as a new build."
                        ),
                        observed_value=f"New build requested for {req.product_context}/{req.market_context}",
                        expected_condition=f"Reuse existing certified asset ({cert_ids[0]})",
                        recommended_action=f"Route request {req.request_id} to certified asset {cert_ids[0]} ({matching_certified[0].asset_name}) before approving new development.",
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        return findings

