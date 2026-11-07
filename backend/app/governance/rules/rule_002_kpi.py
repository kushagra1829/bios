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
from backend.app.models.governance import KpiCatalog, AssetKpiMap
from backend.app.models.core import AnalyticsAssets


class CanonicalKpiRule(BaseGovernanceRule):
    """
    RULE-002 — Canonical KPI first.
    Operational requirement: Use approved KPI definitions unless an exception is
    explicitly documented. Detect non-canonical metrics, unapproved/draft variants,
    definition conflicts, and assets consuming unapproved KPIs.
    """

    rule_id = RuleId.RULE_002
    rule_name = "Canonical KPI first"
    rule_description = "Use approved KPI definitions unless an exception is explicitly documented."
    priority = "high"
    category = "semantic_governance"
    target_entities = ["kpi", "asset"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        # 1. Evaluate KPI Catalog entries that deviate from approved canonical standard
        kpis = db.query(KpiCatalog).all()
        canonical_map: Dict[str, str] = {}  # metric_name -> canonical kpi_id

        for k in kpis:
            if k.approval_status == "approved" and k.definition_status == "canonical":
                canonical_map[k.kpi_name] = k.kpi_id

        for kpi in kpis:
            is_non_canonical = (
                kpi.approval_status != "approved" or kpi.definition_status != "canonical"
            )

            if is_non_canonical:
                severity = (
                    FindingSeverity.CRITICAL
                    if kpi.business_criticality in ("critical", "high")
                    else FindingSeverity.HIGH
                )

                ref = create_evidence_reference(
                    source_table="kpi_catalog",
                    record_id=kpi.kpi_id,
                    field_name="approval_status,definition_status",
                    observed_value=f"{kpi.approval_status} / {kpi.definition_status}",
                    expected_condition="approval_status == 'approved' AND definition_status == 'canonical'",
                    metadata={
                        "domain": kpi.domain,
                        "business_criticality": kpi.business_criticality,
                        "kpi_name": kpi.kpi_name,
                    },
                )

                bundle = create_evidence_bundle(
                    primary_reference=ref,
                    context_notes=(
                        f"KPI '{kpi.kpi_name}' is classified as {kpi.definition_status} "
                        f"with approval status '{kpi.approval_status}'."
                    ),
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.KPI,
                        target_entity_id=kpi.kpi_id,
                        category=self.category,
                        severity=severity,
                        status=FindingStatus.OPEN,
                        title=f"Non-canonical KPI '{kpi.kpi_name}' ({kpi.definition_status})",
                        explanation=(
                            f"KPI {kpi.kpi_id} ('{kpi.kpi_name}') in domain '{kpi.domain}' is not approved "
                            f"(status: '{kpi.approval_status}', definition: '{kpi.definition_status}'). "
                            "Unapproved KPI definitions introduce conflicting metrics across pharma reporting."
                        ),
                        observed_value=f"status: {kpi.approval_status}, definition: {kpi.definition_status}",
                        expected_condition="Approved canonical KPI definition in central catalog",
                        recommended_action=(
                            f"Align or decommission {kpi.kpi_id} in favor of canonical standard, "
                            "or submit for formal governance approval."
                        ),
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        # 2. Evaluate Assets mapped to non-approved / non-canonical KPIs
        non_canonical_kpi_ids = {
            k.kpi_id for k in kpis if k.approval_status != "approved" or k.definition_status != "canonical"
        }

        if non_canonical_kpi_ids:
            # Query mappings to non-canonical KPIs
            bad_mappings = (
                db.query(AssetKpiMap)
                .filter(AssetKpiMap.kpi_id.in_(non_canonical_kpi_ids))
                .all()
            )

            # Group by asset_id to avoid spamming multiple findings per asset
            asset_to_bad_kpis: Dict[str, List[AssetKpiMap]] = {}
            for m in bad_mappings:
                asset_to_bad_kpis.setdefault(m.asset_id, []).append(m)

            for asset_id, maps in asset_to_bad_kpis.items():
                asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_id).first()
                if not asset:
                    continue

                bad_kpi_ids = [m.kpi_id for m in maps]
                primary_ref = create_evidence_reference(
                    source_table="asset_kpi_map",
                    record_id=f"{asset_id}:{maps[0].kpi_id}",
                    field_name="kpi_id",
                    observed_value=bad_kpi_ids,
                    expected_condition="All mapped KPIs must be canonical and approved",
                    metadata={"usage_role": maps[0].usage_role, "asset_name": asset.asset_name},
                )

                corroborating = [
                    create_evidence_reference(
                        source_table="kpi_catalog",
                        record_id=m.kpi_id,
                        field_name="approval_status",
                        observed_value="unapproved/local",
                        expected_condition="approved",
                    )
                    for m in maps[:3]
                ]

                bundle = create_evidence_bundle(
                    primary_reference=primary_ref,
                    corroborating_references=corroborating,
                    context_notes=f"Asset maps to {len(bad_kpi_ids)} non-canonical KPI(s): {', '.join(bad_kpi_ids)}",
                )

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.ASSET,
                        target_entity_id=asset.asset_id,
                        category=self.category,
                        severity=FindingSeverity.HIGH if asset.endorsement in ("certified", "promoted") else FindingSeverity.MEDIUM,
                        status=FindingStatus.OPEN,
                        title=f"Asset uses {len(bad_kpi_ids)} non-canonical KPI(s)",
                        explanation=(
                            f"Asset {asset.asset_id} ('{asset.asset_name}') references non-canonical or "
                            f"unapproved KPI(s): {', '.join(bad_kpi_ids)}. Production reports must consume "
                            "governed canonical metrics."
                        ),
                        observed_value=f"Mapped KPIs: {', '.join(bad_kpi_ids)}",
                        expected_condition="All mapped metrics are approved canonical KPIs",
                        recommended_action=(
                            f"Remap asset {asset.asset_id} to certified canonical KPIs before next release."
                        ),
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        return findings

