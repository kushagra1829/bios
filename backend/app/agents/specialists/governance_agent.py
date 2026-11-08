import logging
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session

from backend.app.agents.entity_catalog import expand_market_scope
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveredAsset,
    DiscoveryResult,
    KpiAnalysisResult,
    DuplicationResult,
    GeographyStatus,
    GovernanceAgentResult,
)
from backend.app.models.governance import GovernanceFindings, KpiCatalog
from backend.app.models.core import AnalyticsAssets, SemanticModels

logger = logging.getLogger(__name__)


class GovernanceAgent:
    """
    Specialist Agent 5: Governance Guardrails.
    Evaluates enterprise governance compliance against the Milestone 1 governance engine.
    Checks ownership, endorsement, lineage, and KPI approval across discovered candidate assets.
    Surfaces hard blockers (prohibiting unmitigated execution) and warnings with traceable evidence.
    """

    agent_name = "GovernanceAgent"

    def process(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        duplication: DuplicationResult,
        db: Session,
    ) -> GovernanceAgentResult:
        logger.info(f"[{self.agent_name}] Evaluating governance constraints for request")

        blockers: List[str] = []
        warnings: List[str] = []
        applicable_rules: Set[str] = set()
        active_findings: List[str] = []
        request_findings: List[str] = []
        out_of_scope_findings: List[str] = []
        out_of_scope_warnings: List[str] = []
        evidence_refs: List[Dict[str, Any]] = []

        # 1. Evaluate KPI Governance (RULE-002: Canonical KPI first)
        applicable_rules.add("RULE-002")
        if kpi_analysis.unapproved_or_conflicted_kpi_ids:
            for bad_id in kpi_analysis.unapproved_or_conflicted_kpi_ids:
                kpi = db.query(KpiCatalog).filter(KpiCatalog.kpi_id == bad_id).first()
                if kpi and kpi.business_criticality in ("critical", "high"):
                    blockers.append(
                        f"RULE-002 BLOCKER: Requested KPI {bad_id} ('{kpi.kpi_name}') is {kpi.definition_status} "
                        f"with approval status '{kpi.approval_status}'. High-criticality unapproved KPIs cannot be deployed to production."
                    )
                else:
                    warnings.append(
                        f"RULE-002 WARNING: KPI {bad_id} is unapproved/local. Formal governance approval required."
                    )
                evidence_refs.append({"table": "kpi_catalog", "id": bad_id, "rule": "RULE-002"})

        # 2. Check Candidate Assets against Milestone 1 Active Governance Findings
        candidate_ids = [a.asset_id for a in discovery.exact_matches + discovery.partial_matches[:5]]
        if candidate_ids:
            findings = (
                db.query(GovernanceFindings)
                .filter(
                    GovernanceFindings.target_entity_id.in_(candidate_ids),
                    GovernanceFindings.status.in_(["open", "persisting"]),
                )
                .all()
            )

            request_asset_ids = self._request_asset_ids(intent, discovery, duplication, db)
            for f in findings:
                active_findings.append(f.finding_id)
                applicable_rules.add(f.rule_id)

                if f.target_entity_id not in request_asset_ids:
                    out_of_scope_findings.append(f.finding_id)
                    if f.severity in ("critical", "high"):
                        out_of_scope_warnings.append(
                            f"{f.rule_id} on {f.target_entity_id}, outside the requested scope: {f.title}."
                        )
                    evidence_refs.append({
                        "finding_id": f.finding_id,
                        "target_id": f.target_entity_id,
                        "rule_id": f.rule_id,
                        "severity": f.severity,
                        "scope": "outside_request",
                    })
                    continue

                request_findings.append(f.finding_id)
                if f.severity == "critical":
                    blockers.append(
                        f"{f.rule_id} BLOCKER on {f.target_entity_id}: {f.title}. Rationale: {f.explanation}"
                    )
                elif f.severity == "high":
                    warnings.append(
                        f"{f.rule_id} HIGH WARNING on {f.target_entity_id}: {f.title}."
                    )
                evidence_refs.append({
                    "finding_id": f.finding_id,
                    "target_id": f.target_entity_id,
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "scope": "request",
                })

        # 3. Check Reuse Before Build (RULE-001)
        applicable_rules.add("RULE-001")
        if discovery.exact_matches:
            endorsed = [a for a in discovery.exact_matches if a.endorsement in ("certified", "promoted")]
            endorsed.sort(key=lambda a: 0 if a.endorsement == "certified" else 1)  # stable: keeps discovery order within a level
            top_exact = endorsed[0] if endorsed else discovery.exact_matches[0]
            if top_exact.endorsement in ("certified", "promoted"):
                warnings.append(
                    f"RULE-001 DIRECTIVE: {top_exact.endorsement.capitalize()} asset {top_exact.asset_id} ('{top_exact.asset_name}') "
                    "already serves this exact scope. Reuse must be prioritized before building new analytics."
                )

        # 4. Check Ownership Integrity (RULE-003)
        applicable_rules.add("RULE-003")
        for asset_summary in discovery.exact_matches:
            asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_summary.asset_id).first()
            if asset and asset.owner_id is None:
                blockers.append(
                    f"RULE-003 BLOCKER: Asset {asset.asset_id} has no assigned owner. Unowned assets cannot be extended."
                )

        logger.info(
            f"[{self.agent_name}] Governance check complete: {len(blockers)} blocker(s), "
            f"{len(warnings)} warning(s), {len(active_findings)} active finding(s)"
        )

        return GovernanceAgentResult(
            blockers=blockers,
            warnings=warnings,
            applicable_rule_ids=sorted(list(applicable_rules)),
            active_finding_ids=active_findings,
            human_approval_required=True,  # Human approval always required for consequential changes
            evidence_references=evidence_refs,
            request_finding_ids=request_findings,
            out_of_scope_finding_ids=out_of_scope_findings,
            out_of_scope_warnings=out_of_scope_warnings,
        )

    @staticmethod
    def _request_asset_ids(
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        duplication: DuplicationResult,
        db: Session,
    ) -> Set[str]:
        """
        Assets whose findings can block this request: those matching its products and markets,
        plus any asset the Decision Agent may recommend as a target, which is a direct dependency.
        A stated geography limits scope even when none of it resolved. No stated geography doesn't.
        """
        geography = intent.geography
        unresolved = bool(geography) and geography.status in (
            GeographyStatus.NEEDS_CLARIFICATION,
            GeographyStatus.PARTIALLY_RESOLVED,
        )
        market_limited = bool(intent.markets) or unresolved
        market_scope = expand_market_scope(intent.markets, db)
        products = [p.lower() for p in intent.products]

        def in_scope(asset: DiscoveredAsset) -> bool:
            product_ok = not products or any(
                p in asset.product_scope.lower() or p in asset.asset_name.lower() for p in products
            )
            return product_ok and (not market_limited or asset.market_scope.lower() in market_scope)

        candidates = discovery.exact_matches + discovery.partial_matches
        asset_ids = {asset.asset_id for asset in candidates if in_scope(asset)}
        # Unresolved geography gets no target, so it has no target dependency either.
        if not unresolved:
            if duplication.primary_duplicate_asset_id:
                asset_ids.add(duplication.primary_duplicate_asset_id)
            if not discovery.exact_matches and discovery.partial_matches:
                asset_ids.add(discovery.partial_matches[0].asset_id)
        return asset_ids

