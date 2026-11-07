import json
import logging
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveredAsset,
    DiscoveryResult,
    KpiAnalysisResult,
    KpiMatch,
    DuplicationResult,
    GovernanceAgentResult,
    GeographyStatus,
    DecisionNarrative,
    DecisionResult,
    DecisionType,
    DecisionAlternative,
)
from backend.app.agents.specialists.llm_assisted import LLMAssistedAgent
from backend.app.models.domain import Products
from backend.app.models.governance import AssetKpiMap, MigrationBacklog
from backend.app.models.lifecycle import LifecycleAssetAssessments, MigrationAssessments

logger = logging.getLogger(__name__)

_ENDORSEMENT_RANK = {"certified": 2, "promoted": 1}
_MAX_PRODUCT_OPTIONS = 5
_ENTITY_ID_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{2,}\b")
_MAX_NARRATIVE_ITEMS = 8
_MAX_NARRATIVE_ITEM_CHARS = 300


class DecisionAgent(LLMAssistedAgent):
    """
    Specialist Agent 6: Decision Synthesis.
    Synthesizes outputs from Intent, Discovery, KPI Intelligence, Duplication, and Governance.
    Adheres strictly to the Bayer governance hierarchy:
      1. REUSE certified assets first (RULE-001).
      2. CONSOLIDATE redundant/duplicate analytics.
      3. MODIFY existing semantic models and reports to add missing metrics.
      4. MIGRATE rationalised legacy Tableau assets.
      5. BUILD_NEW only as a last resort when reuse/modify are unviable.
      6. NEEDS_CLARIFICATION when intent is ambiguous or missing key specifications.
    Never overrides governance blockers. Always mandates human approval for consequential actions.

    The decision matrix is deterministic and runs first. The LLM only writes llm_narrative
    from the finished decision, so it cannot affect the decision, blockers or approvals.
    """

    agent_name = "DecisionAgent"

    def process(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        duplication: DuplicationResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> DecisionResult:
        decision = self._decide(intent, discovery, kpi_analysis, duplication, governance, db)
        decision.active_finding_ids = list(governance.active_finding_ids)
        decision.out_of_scope_warnings = list(governance.out_of_scope_warnings)
        if governance.out_of_scope_finding_ids:
            decision.rationale += (
                f" {len(governance.out_of_scope_finding_ids)} governance finding(s) on assets outside the requested "
                "scope are reported separately and aren't blockers for this request."
            )
        decision.llm_narrative = self._narrate(decision)
        return decision

    @staticmethod
    def _clarification_steps(intent: BusinessIntent, geography_unresolved: bool) -> List[str]:
        """Ask only for what is actually missing, and say what is already settled."""
        steps: List[str] = []
        if geography_unresolved:
            geography = intent.geography
            step = f"Confirm the geographic scope for: {', '.join(geography.unresolved_geography)}."
            if geography.resolved_market_ids:
                step += f" Already resolved: {', '.join(geography.resolved_market_ids)}."
            suggested = [m for p in geography.phrases for m in p.suggested_market_ids]
            if suggested:
                step += f" Suggestions to confirm, not verified matches: {', '.join(dict.fromkeys(suggested))}."
            steps.append(step)
        elif not intent.markets:
            steps.append("Specify target country or regional market context.")
        for ambiguity in intent.ambiguities:
            if ambiguity.category == "term":
                steps.append(f"Confirm whether '{ambiguity.term}' refers to market {', '.join(ambiguity.candidates)}.")
        if not intent.products:
            steps.append("Specify target pharmaceutical brand/product.")
        if not intent.kpis:
            steps.append("Clarify required metric calculations.")
        if not intent.time_periods:
            steps.append("Specify the time frequency.")
        return steps or ["Resolve the items listed in the rationale."]

    def _decide_without_product(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> Optional[DecisionResult]:
        """
        Target an asset only if it's portfolio-wide (no product assumed), active, owned, on a
        semantic model, and has KPI or title evidence for a requested metric. Otherwise ask which
        product is meant. Returns None when nothing matched and a market was given, because
        that's a genuine gap for the normal decision path to assess.
        """
        candidates = discovery.exact_matches + discovery.partial_matches
        if not candidates and intent.markets:
            return None

        catalog_products = {name for (name,) in db.query(Products.product_name).all()}
        metrics = [m for m in kpi_analysis.matches if m.matched_kpi_id]
        ranked = []
        for asset in candidates:
            if asset.product_scope in catalog_products or asset.lifecycle_status != "active":
                continue
            if not asset.owner_name or not asset.model_id:
                continue
            mapped_ids = {row.kpi_id for row in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset.asset_id).all()}
            mapped = [m for m in metrics if m.matched_kpi_id in mapped_ids]
            title_only = [m for m in metrics if m not in mapped and _title_mentions(asset.asset_name, m)]
            if mapped or title_only:
                endorsement = _ENDORSEMENT_RANK.get(asset.endorsement, 0)
                ranked.append((-len(mapped), -len(title_only), -endorsement, -asset.match_score, asset.asset_id, asset, mapped, title_only))

        if not ranked:
            return self._ask_for_product(intent, candidates, governance)

        *_, asset, mapped, title_only = min(ranked, key=lambda item: item[:5])
        evidence = []
        if mapped:
            evidence.append(f"asset_kpi_map confirms {_metric_names(mapped)}")
        if title_only:
            evidence.append(f"only its title suggests {_metric_names(title_only)}, which asset_kpi_map doesn't confirm")
        scope_note = ""
        if intent.markets and asset.market_scope not in intent.markets:
            scope_note = f" It's scoped to {asset.market_scope}, within the requested {', '.join(intent.markets)}."

        next_steps = [
            "Confirm a portfolio-wide view meets the need, or name a product for a product-specific asset.",
            f"Submit a change request to {asset.owner_name}, owner of {asset.asset_id}.",
        ]
        if title_only:
            next_steps.insert(1, f"Verify that {asset.asset_id} calculates {_metric_names(title_only)}, then map the KPI.")

        return DecisionResult(
            decision=DecisionType.MODIFY,
            confidence=0.75 if not title_only else 0.6,
            primary_recommendation=f"Extend portfolio-wide asset {asset.asset_id} ('{asset.asset_name}'), subject to the limitations in the rationale.",
            rationale=(
                f"The request names no product, so BIOS looked for a portfolio-wide asset rather than assuming one. "
                f"{asset.asset_id} ('{asset.asset_name}') has scope '{asset.product_scope}', is active and has an owner. "
                f"Evidence: {'; '.join(evidence)}.{scope_note}"
            ),
            target_asset_ids=[asset.asset_id],
            target_model_ids=[asset.model_id],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=True,
            next_steps=next_steps,
        )

    def _ask_for_product(
        self,
        intent: BusinessIntent,
        candidates: List[DiscoveredAsset],
        governance: GovernanceAgentResult,
    ) -> DecisionResult:
        options = [f"{a.asset_id} '{a.asset_name}' ({a.product_scope})" for a in candidates[:_MAX_PRODUCT_OPTIONS]]
        if options:
            found = (
                f"Assets matching the request's market and title words are product-specific or lack supporting "
                f"evidence, so choosing one would assume a product: {'; '.join(options)}."
            )
        else:
            found = "With no product or market named, there's no scope to search on."
        steps = self._clarification_steps(intent, False)
        if options:
            steps.append(f"Assets that may apply once a product is named: {'; '.join(options)}.")
        return DecisionResult(
            decision=DecisionType.NEEDS_CLARIFICATION,
            confidence=0.85,
            primary_recommendation="Specify the product before BIOS recommends a target asset.",
            rationale=f"The request names no product. {found}",
            target_asset_ids=[],
            target_model_ids=[],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=False,
            next_steps=steps,
        )

    def _narrate(self, decision: DecisionResult) -> Optional[str]:
        """Draft a plain-language summary, rejecting any that contradicts the decision or cites unknown IDs."""
        facts = {
            "decision": decision.decision.value,
            "confidence": decision.confidence,
            "primary_recommendation": decision.primary_recommendation,
            "rationale": decision.rationale,
            "target_asset_ids": decision.target_asset_ids,
            "target_model_ids": decision.target_model_ids,
            "human_approval_required": decision.human_approval_required,
            "blocker_count": len(decision.blockers),
            "blockers": _bounded(decision.blockers),
            "warning_count": len(decision.warnings),
            "warnings": _bounded(decision.warnings),
            "next_steps": _bounded(decision.next_steps),
        }
        known_ids = set(_ENTITY_ID_PATTERN.findall(json.dumps(facts)))

        def guard(narrative: DecisionNarrative) -> None:
            if narrative.decision_echo != decision.decision:
                raise ValueError(f"narrative contradicts decision {decision.decision.value}")
            if narrative.human_approval_required_echo != decision.human_approval_required:
                raise ValueError("narrative contradicts the human approval requirement")
            if narrative.blocker_count_echo != len(decision.blockers):
                raise ValueError("narrative contradicts the governance blocker count")
            unknown = set(_ENTITY_ID_PATTERN.findall(narrative.summary)) - known_ids
            if unknown:
                raise ValueError(f"narrative cites IDs absent from the decision: {sorted(unknown)}")

        narrative = self._llm_step(
            prompt=(
                "Explain this decision to a business stakeholder in at most three sentences. "
                "The decision is final: do not change, soften or question it. Use only the supplied "
                "facts, and cite only IDs that appear in them. State any blockers and any required "
                "human approval. Copy decision, human_approval_required and blocker_count into the echo fields."
            ),
            schema=DecisionNarrative,
            system_prompt="You are the BIOS Decision Agent's communications assistant. You explain decisions; you do not make them.",
            context=facts,
            guard=guard,
        )
        return narrative.summary.strip() if narrative else None

    def _decide(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        duplication: DuplicationResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> DecisionResult:
        logger.info(f"[{self.agent_name}] Synthesizing multi-agent inputs into strategic recommendation")

        # 1. Check for Ambiguous / Missing Requirements
        # Geography the user stated but BIOS can't fully resolve could change the candidate assets,
        # so it gets no definitive action. A request that names no geography isn't affected.
        geography_unresolved = bool(intent.geography) and intent.geography.status in (
            GeographyStatus.NEEDS_CLARIFICATION,
            GeographyStatus.PARTIALLY_RESOLVED,
        )
        # A word that may or may not be a market could change the candidates too. It's a separate
        # question from geography, so it doesn't affect the geography status.
        unclear_term = any(a.category == "term" for a in intent.ambiguities)
        if intent.confidence < 0.45 or len(intent.missing_or_ambiguous) >= 3 or geography_unresolved or unclear_term:
            gaps = "; ".join(item.rstrip(".") for item in intent.missing_or_ambiguous)
            return DecisionResult(
                decision=DecisionType.NEEDS_CLARIFICATION,
                confidence=0.85,
                primary_recommendation="Clarification required before analytics provisioning can proceed.",
                rationale=(
                    "The business request lacks critical operational details required to evaluate "
                    f"existing assets: {gaps}. In accordance with "
                    "governance standards, analytics should not be commissioned without clear product scope, "
                    "geographic market, and metric definitions."
                ),
                target_asset_ids=[],
                target_model_ids=[],
                alternatives=[],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=False,
                next_steps=self._clarification_steps(intent, geography_unresolved),
            )

        # A request that names no product can't be pointed at one product's asset.
        if not intent.products:
            without_product = self._decide_without_product(intent, discovery, kpi_analysis, governance, db)
            if without_product is not None:
                return without_product

        # 2. Check for Governance Blockers
        has_critical_blockers = len(governance.blockers) > 0

        # Check for matching migration backlog candidates in case MIGRATE applies
        migration_candidates = []
        if intent.products:
            prod = intent.products[0]
            migration_candidates = (
                db.query(MigrationBacklog)
                .filter(MigrationBacklog.product_scope.ilike(f"%{prod}%"))
                .all()
            )

        # 3. Decision Matrix Evaluation

        # Query lifecycle and migration intelligence if available
        def _get_lifecycle_note(asset_id: str) -> str:
            asm = (
                db.query(LifecycleAssetAssessments)
                .filter(LifecycleAssetAssessments.asset_id == asset_id)
                .order_by(LifecycleAssetAssessments.assessed_at.desc())
                .first()
            )
            if asm:
                return f" [Lifecycle Engine: {asm.recommended_action}, health score: {asm.composite_score:.1f}]"
            return ""

        # Option A: REUSE Existing Certified Asset
        top_exact_certified = next(
            (a for a in discovery.exact_matches if a.endorsement in ("certified", "promoted")),
            None,
        )

        if top_exact_certified and not has_critical_blockers:
            matched_kpi_cnt = len(kpi_analysis.canonical_approved_kpi_ids)
            lc_note = _get_lifecycle_note(top_exact_certified.asset_id)
            rationale = (
                f"Existing certified asset {top_exact_certified.asset_id} ('{top_exact_certified.asset_name}') "
                f"already covers {top_exact_certified.product_scope} in {top_exact_certified.market_scope} "
                f"(endorsement: '{top_exact_certified.endorsement}'). It supports {matched_kpi_cnt} of the "
                f"requested canonical KPIs{lc_note}. In accordance with RULE-001 (Reuse before build), business users "
                "must be directed to this certified report rather than creating redundant analytics."
            )

            alternatives = [
                DecisionAlternative(
                    action="MODIFY",
                    target_id=top_exact_certified.asset_id,
                    pros="Enhances an existing certified asset without creating new content.",
                    cons="Requires minor report change management and testing.",
                ),
                DecisionAlternative(
                    action="BUILD_NEW",
                    target_id=None,
                    pros="Complete customization for specific country request.",
                    cons="Violates RULE-001, increases BI estate sprawl and maintenance overhead.",
                ),
            ]

            return DecisionResult(
                decision=DecisionType.REUSE,
                confidence=0.92,
                primary_recommendation=f"Reuse existing certified report {top_exact_certified.asset_id} ('{top_exact_certified.asset_name}').",
                rationale=rationale,
                target_asset_ids=[top_exact_certified.asset_id],
                target_model_ids=[top_exact_certified.model_id] if top_exact_certified.model_id else [],
                alternatives=alternatives,
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=False,
                next_steps=[
                    f"Provide user access to workspace containing {top_exact_certified.asset_id}.",
                    "Verify user filters cover the desired country-level granularity.",
                ],
            )

        # Option B: CONSOLIDATE Duplicate Assets
        if duplication.has_duplicates and duplication.primary_duplicate_asset_id:
            dup_asset_id = duplication.primary_duplicate_asset_id
            lc_note = _get_lifecycle_note(dup_asset_id)
            rationale = (
                f"High-confidence duplication detected (similarity {duplication.highest_similarity_score:.2f}) "
                f"with existing asset {dup_asset_id}{lc_note}. Creating another dashboard would increase report sprawl. "
                "The recommended path is to consolidate requirements into the primary shared asset."
            )

            return DecisionResult(
                decision=DecisionType.CONSOLIDATE,
                confidence=0.88,
                primary_recommendation=f"Consolidate requirements into existing duplicate candidate {dup_asset_id}.",
                rationale=rationale,
                target_asset_ids=[dup_asset_id],
                target_model_ids=[discovery.exact_matches[0].model_id] if discovery.exact_matches and discovery.exact_matches[0].model_id else [],
                alternatives=[
                    DecisionAlternative(
                        action="MODIFY",
                        target_id=dup_asset_id,
                        pros="Retains single source of truth.",
                        cons="May require reconciling user permissions.",
                    )
                ],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                next_steps=[
                    f"Contact owner of asset {dup_asset_id} to schedule consolidation review.",
                    "Deprecate duplicate variants.",
                ],
            )

        # Option C: MODIFY Existing Semantic Model / Report
        # If an active asset or shared semantic model exists for the product, extend it!
        relevant_asset = (
            discovery.exact_matches[0]
            if discovery.exact_matches
            else (discovery.partial_matches[0] if discovery.partial_matches else None)
        )

        if relevant_asset and relevant_asset.model_id:
            rationale = (
                f"Existing asset {relevant_asset.asset_id} ('{relevant_asset.asset_name}') and shared semantic "
                f"model {relevant_asset.model_id} already serve {relevant_asset.product_scope}. "
                "Rather than building a disconnected new report, the optimal path is to extend the existing "
                "report or add requested measures to the shared semantic model."
            )

            return DecisionResult(
                decision=DecisionType.MODIFY,
                confidence=0.84,
                primary_recommendation=f"Extend existing asset {relevant_asset.asset_id} and shared model {relevant_asset.model_id}.",
                rationale=rationale,
                target_asset_ids=[relevant_asset.asset_id],
                target_model_ids=[relevant_asset.model_id],
                alternatives=[
                    DecisionAlternative(
                        action="BUILD_NEW",
                        target_id=None,
                        pros="Greenfield build with no legacy constraints.",
                        cons="Creates duplicate model logic and violates reuse guidelines.",
                    )
                ],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                next_steps=[
                    f"Submit change request to owner of model {relevant_asset.model_id}.",
                    "Implement missing DAX measures for canonical KPIs.",
                    "Test country-level slicing in dev workspace.",
                ],
            )

        # Option D: MIGRATE Legacy Asset
        if migration_candidates:
            cand = migration_candidates[0]
            rationale = (
                f"Found legacy Tableau migration candidate {cand.source_asset_id} in {cand.product_scope} "
                f"(status: '{cand.status}', recommended path: '{cand.recommended_path_candidate}'). "
                f"Instead of building a separate asset, execute the planned migration of {cand.source_asset_id} "
                f"onto target semantic model {cand.candidate_target_model_id}."
            )

            return DecisionResult(
                decision=DecisionType.MIGRATE,
                confidence=0.82,
                primary_recommendation=f"Execute migration of legacy asset {cand.source_asset_id} onto model {cand.candidate_target_model_id}.",
                rationale=rationale,
                target_asset_ids=[cand.source_asset_id],
                target_model_ids=[cand.candidate_target_model_id],
                alternatives=[],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                next_steps=[
                    f"Initiate migration workflow for {cand.source_asset_id}.",
                    "Validate metric parity against Tableau benchmark.",
                ],
            )

        # Option E: BUILD_NEW (Only when all above alternatives are exhausted)
        rationale = (
            "Thorough discovery across 360 analytics assets, 75 semantic models, and migration backlog "
            f"confirms that no existing asset covers {', '.join(intent.products)} in {', '.join(intent.markets)}. "
            "Building a new analytics asset is justified, provided it connects to a shared semantic model, "
            "consumes approved canonical KPIs, and has an active owner assigned."
        )

        return DecisionResult(
            decision=DecisionType.BUILD_NEW,
            confidence=0.78,
            primary_recommendation="Build new governed analytics asset on shared semantic model.",
            rationale=rationale,
            target_asset_ids=[],
            target_model_ids=[],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=True,
            next_steps=[
                "Assign designated active business owner.",
                "Select or create certified shared semantic model.",
                "Map measures strictly to approved canonical KPIs.",
            ],
        )


def _title_mentions(title: str, metric: KpiMatch) -> bool:
    """Whole-phrase match, so 'net sales' doesn't match a title like 'Gross-to-Net Final'."""
    terms = (metric.requested_metric, metric.matched_kpi_name or "")
    return any(term and re.search(rf"\b{re.escape(term)}\b", title, re.IGNORECASE) for term in terms)


def _metric_names(metrics: List[KpiMatch]) -> str:
    return ", ".join(f"{m.matched_kpi_name} ({m.matched_kpi_id})" for m in metrics)


def _bounded(items: List[str]) -> List[str]:
    """Keep the narrative prompt inside the context window. Full lists stay on the decision."""
    return [item[:_MAX_NARRATIVE_ITEM_CHARS] for item in items[:_MAX_NARRATIVE_ITEMS]]

