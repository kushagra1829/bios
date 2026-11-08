import logging
from typing import List, Optional, Set, Dict, Any
from sqlalchemy.orm import Session

from backend.app.agents.entity_catalog import expand_market_scope
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    KpiAnalysisResult,
    DuplicationResult,
    DuplicateCandidate,
)
from backend.app.agents.specialists.duplication_gates import DuplicateGateEngine
from backend.app.models.core import AnalyticsAssets, SemanticModels
from backend.app.models.governance import AssetKpiMap

logger = logging.getLogger(__name__)

PORTFOLIO_WIDE_SCOPES = {"portfolio-wide", "cross-product", "all products", "global portfolio", "enterprise"}


class DuplicationAgent:
    """
    Specialist Agent 4: Duplication Intelligence.
    Evaluates whether the requested analytics duplicate existing reports in the enterprise.
    Multi-factor similarity scoring with Enterprise Validation Gates G1–G4:
      - Gate G1: Scope Compatibility (Product and market scope alignment).
      - Gate G2: Canonical Concept Overlap (Jaccard similarity of governed metric groups).
      - Gate G3: Exact Metric Overlap vs Metric Drift.
      - Gate G4: Structural Lineage & Semantic Model Sharing.
    
    Enterprise Enhancements:
      - Vetoes consolidation on scope mismatch (Gate G1).
      - Detects metric drift when title keywords match but mapped KPIs are disjoint (Gate G3).
      - Distinguishes duplicate candidates for human review from confirmed duplicates.
      - Never automatically recommends asset retirement based purely on similarity heuristics.
    """

    agent_name = "DuplicationAgent"

    WEIGHT_STRUCTURAL = 0.45
    WEIGHT_KPI = 0.35
    WEIGHT_SEMANTIC = 0.20
    DUPLICATE_THRESHOLD = 0.65

    def process(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        db: Session,
    ) -> DuplicationResult:
        logger.info(f"[{self.agent_name}] Evaluating duplication across {len(discovery.exact_matches) + len(discovery.partial_matches)} candidate assets")

        candidate_assets = discovery.exact_matches + discovery.partial_matches
        if not candidate_assets:
            return DuplicationResult(
                has_duplicates=False,
                candidates=[],
                highest_similarity_score=0.0,
                primary_duplicate_asset_id=None,
                explanation="No existing assets identified with sufficient scope overlap to assess duplication.",
            )

        requested_kpi_ids = set(kpi_analysis.canonical_approved_kpi_ids)
        products_lower = {p.lower() for p in intent.products}
        markets_lower = expand_market_scope(intent.markets, db)
        is_global_intent = any(m.lower() in ("global", "worldwide", "all", "enterprise") for m in intent.markets)
        duplicate_candidates: List[DuplicateCandidate] = []

        for candidate in candidate_assets:
            asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == candidate.asset_id).first()
            if not asset:
                continue

            asset_prod = (asset.product_scope or "").lower()
            asset_mkt = (asset.market_scope or "").lower()

            # Gate G1: Scope Compatibility Check
            is_portfolio_wide = any(term in asset_prod for term in PORTFOLIO_WIDE_SCOPES)
            is_global_asset = asset_mkt in ("global", "worldwide", "all", "enterprise")
            prod_match = any(p in asset_prod for p in products_lower) if products_lower else True
            mkt_match = is_global_intent or is_global_asset or (any(m in asset_mkt or asset_mkt in m for m in markets_lower) if markets_lower else True)

            scope_compatible = (prod_match or is_portfolio_wide) and mkt_match
            if products_lower and not prod_match and not is_portfolio_wide and asset_prod:
                # Explicit product conflict: Gate G1 fails!
                scope_compatible = False

            # 1. Structural Similarity (45% weight)
            # Checks if asset uses a central shared semantic model and enterprise workspace
            structural_score = 0.0
            structural_reasons = []

            if candidate.model_id:
                model = db.query(SemanticModels).filter(SemanticModels.model_id == candidate.model_id).first()
                if model:
                    if products_lower and any(p in model.product_scope.lower() for p in products_lower):
                        structural_score += 0.6
                        structural_reasons.append(f"Shares product semantic model {model.model_id} ('{model.model_name}')")
                    elif not products_lower:
                        structural_score += 0.4
                    if model.endorsement in ("certified", "promoted"):
                        structural_score += 0.4
                        structural_reasons.append(f"Semantic model is endorsed as '{model.endorsement}'")
            structural_score = min(1.0, structural_score)

            # 2. KPI Similarity & Metric Drift Analysis (35% weight)
            kpi_score = 0.0
            kpi_reasons = []
            asset_maps = db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == candidate.asset_id).all()
            asset_kpi_ids = {m.kpi_id for m in asset_maps}

            metric_drift_detected = False
            if requested_kpi_ids and asset_kpi_ids:
                intersection = requested_kpi_ids.intersection(asset_kpi_ids)
                overlap_ratio = len(intersection) / len(requested_kpi_ids)
                kpi_score = round(overlap_ratio, 2)
                if intersection:
                    kpi_reasons.append(f"Shares {len(intersection)} requested KPI(s): {', '.join(intersection)}")
                elif candidate.match_score >= 0.5:
                    # Shared scope or title words but 0 shared mapped KPIs -> Gate G3 Metric Drift
                    metric_drift_detected = True
                    kpi_reasons.append("Zero exact shared KPIs despite scope alignment; potential metric drift (Gate G3)")
            elif not requested_kpi_ids and asset_kpi_ids:
                kpi_score = 0.3
            kpi_score = min(1.0, kpi_score)

            # 3. Semantic / Title Similarity (20% weight)
            semantic_score = candidate.match_score
            semantic_reasons = candidate.match_reasons

            # Composite weighted similarity score
            composite_score = round(
                (self.WEIGHT_STRUCTURAL * structural_score)
                + (self.WEIGHT_KPI * kpi_score)
                + (self.WEIGHT_SEMANTIC * semantic_score),
                2,
            )

            # Gate G1 Scope Penalty
            if not scope_compatible:
                composite_score = min(0.35, composite_score)
                structural_reasons.append("Gate G1 Scope Veto: Product or market scope mismatch prohibits consolidation.")

            candidate_obj = DuplicateCandidate(
                asset_id=candidate.asset_id,
                asset_name=candidate.asset_name,
                similarity_score=composite_score,
                structural_similarity=structural_score,
                kpi_similarity=kpi_score,
                semantic_similarity=semantic_score,
                endorsement=candidate.endorsement,
                lifecycle_status=candidate.lifecycle_status,
                evidence={
                    "scope_compatible": scope_compatible,
                    "metric_drift_detected": metric_drift_detected,
                    "structural_reasons": structural_reasons,
                    "kpi_reasons": kpi_reasons,
                    "semantic_reasons": semantic_reasons,
                    "mapped_kpi_count": len(asset_kpi_ids),
                },
            )
            duplicate_candidates.append(candidate_obj)

        duplicate_candidates.sort(key=lambda x: x.similarity_score, reverse=True)

        # High similarity duplicates require: composite score >= threshold AND scope_compatible
        high_sim_duplicates = [
            c for c in duplicate_candidates
            if c.similarity_score >= self.DUPLICATE_THRESHOLD and c.evidence.get("scope_compatible", True)
        ]
        has_duplicates = len(high_sim_duplicates) > 0
        top_cand = high_sim_duplicates[0] if high_sim_duplicates else (duplicate_candidates[0] if duplicate_candidates else None)
        top_score = top_cand.similarity_score if top_cand else 0.0

        explanation = (
            f"Found {len(high_sim_duplicates)} high-confidence duplicate asset(s) (similarity >= {self.DUPLICATE_THRESHOLD}). "
            f"Top match: {top_cand.asset_id} ('{top_cand.asset_name}') with composite similarity {top_score:.2f}."
            if has_duplicates
            else "No high-confidence duplicates detected. Existing assets have distinct structural scope, incompatible domains, or disjoint KPI mappings."
        )

        result = DuplicationResult(
            has_duplicates=has_duplicates,
            candidates=duplicate_candidates[:8],
            highest_similarity_score=top_score,
            primary_duplicate_asset_id=top_cand.asset_id if (top_cand and has_duplicates) else None,
            explanation=explanation,
        )
        self._evaluate_estate_pairs(intent, db, result)
        logger.info(f"[{self.agent_name}] {result.explanation}")
        return result

    @staticmethod
    def _title_root(name: str) -> str:
        tokens = name.lower().replace(" - ", " ").split()
        return " ".join(t for t in tokens if t not in {"copy", "final", "v2", "legacy", "new", "monthly", "us", "global", "emea"})

    def _evaluate_estate_pairs(self, intent: BusinessIntent, db: Session, result: DuplicationResult) -> None:
        """
        Staged G1-G4 gates over existing assets in the requested scope. A pair is consolidation
        evidence only when the gates pass: same product and market (G1), overlapping governed concepts
        (G2) and no metric drift (G3). Same-titled assets in different scopes are listed with the gate
        that rejected them, so a similar title is never mistaken for a duplicate.
        """
        if not intent.products or any(p.lower() == "all pharma" for p in intent.products):
            return
        markets = expand_market_scope(intent.markets, db) if intent.markets else set()
        if any(m.lower() == "global" for m in intent.markets):
            markets = set()  # Global covers every market scope
        query = db.query(AnalyticsAssets).filter(AnalyticsAssets.product_scope.in_(list(intent.products)))
        assets = [a for a in query.order_by(AnalyticsAssets.asset_id).all() if not markets or a.market_scope.lower() in markets]
        if len(assets) < 2:
            return

        by_scope: Dict[tuple, List[AnalyticsAssets]] = {}
        for a in assets:
            by_scope.setdefault((a.product_scope, a.market_scope), []).append(a)
        evaluations: List[Dict[str, Any]] = []
        eligible: List[List[str]] = []
        for scoped in by_scope.values():
            for i in range(len(scoped)):
                for j in range(i + 1, len(scoped)):
                    ev = DuplicateGateEngine.evaluate_pair(db, scoped[i].asset_id, scoped[j].asset_id)
                    record = {
                        "pair": list(ev.pair),
                        "scope": f"{scoped[i].product_scope} / {scoped[i].market_scope}",
                        "g1_scope_pass": ev.g1_scope_pass,
                        "g2_canonical_group_jaccard": ev.g2_canonical_group_jaccard,
                        "g3_exact_kpi_jaccard": ev.g3_exact_kpi_jaccard,
                        "g4_shares_model": ev.g4_shares_model,
                        "consolidation_eligible": ev.consolidation_eligible,
                        "recommendation": ev.recommendation,
                        "explanation": ev.explanation,
                    }
                    if ev.consolidation_eligible:
                        eligible.append(list(ev.pair))
                        evaluations.insert(0, record)
                    elif intent.duplication_question:
                        evaluations.append(record)

        groups: Dict[str, List[AnalyticsAssets]] = {}
        for a in assets:
            groups.setdefault(self._title_root(a.asset_name), []).append(a)
        title_groups: List[Dict[str, Any]] = []
        for root, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            markets_in_group = sorted({m.market_scope for m in members})
            pairs = [p for p in eligible if all(x in {m.asset_id for m in members} for x in p)]
            title_groups.append({
                "title_root": root,
                "asset_ids": [m.asset_id for m in members],
                "markets": markets_in_group,
                "consolidation_eligible_pairs": pairs,
                "verdict": (
                    "Gate-confirmed overlap: surface for consolidation review." if pairs else
                    ("Different markets: Gate G1 vetoes consolidation despite the similar title." if len(markets_in_group) > 1
                     else "Same scope but the gates found insufficient KPI overlap or metric drift (G2/G3).")
                ),
            })

        result.gate_evaluations = evaluations[:40]
        result.consolidation_eligible_pairs = eligible
        result.title_alike_groups = title_groups
        summary = (
            f" Staged G1-G4 gates over {len(assets)} in-scope asset(s): {len(eligible)} consolidation-eligible pair(s)"
            + (f" ({'; '.join(' + '.join(p) for p in eligible)})" if eligible else "")
            + f"; {len(title_groups)} same-title group(s) checked."
        )
        result.explanation = (result.explanation + summary).strip()
