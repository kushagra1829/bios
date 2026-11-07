import logging
from typing import List, Optional, Set, Dict, Any
from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    KpiAnalysisResult,
    DuplicationResult,
    DuplicateCandidate,
)
from backend.app.models.core import AnalyticsAssets, SemanticModels
from backend.app.models.governance import AssetKpiMap

logger = logging.getLogger(__name__)


class DuplicationAgent:
    """
    Specialist Agent 4: Duplication Intelligence.
    Evaluates whether the requested analytics duplicate existing reports in the enterprise.
    Multi-factor similarity scoring:
      - Structural similarity (45% weight): shared underlying semantic model, workspace, platform.
      - KPI similarity (35% weight): shared mapped KPIs and governed measures.
      - Semantic similarity (20% weight): title, keywords, and domain purpose.
    Prioritizes structural and KPI evidence over superficial title matches.
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
        duplicate_candidates: List[DuplicateCandidate] = []

        for candidate in candidate_assets:
            asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == candidate.asset_id).first()
            if not asset:
                continue

            # 1. Structural Similarity (45% weight)
            # Checks if asset uses a central shared semantic model and enterprise workspace
            structural_score = 0.0
            structural_reasons = []

            # Check if asset shares target product/market model
            if candidate.model_id:
                model = db.query(SemanticModels).filter(SemanticModels.model_id == candidate.model_id).first()
                if model:
                    if any(p.lower() in model.product_scope.lower() for p in intent.products):
                        structural_score += 0.6
                        structural_reasons.append(f"Shares product semantic model {model.model_id} ('{model.model_name}')")
                    if model.endorsement in ("certified", "promoted"):
                        structural_score += 0.4
                        structural_reasons.append(f"Semantic model is endorsed as '{model.endorsement}'")
            structural_score = min(1.0, structural_score)

            # 2. KPI Similarity (35% weight)
            # Checks overlap of mapped KPIs in asset_kpi_map
            kpi_score = 0.0
            kpi_reasons = []
            asset_maps = db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == candidate.asset_id).all()
            asset_kpi_ids = {m.kpi_id for m in asset_maps}

            if requested_kpi_ids and asset_kpi_ids:
                intersection = requested_kpi_ids.intersection(asset_kpi_ids)
                overlap_ratio = len(intersection) / len(requested_kpi_ids)
                kpi_score = round(overlap_ratio, 2)
                if intersection:
                    kpi_reasons.append(f"Shares {len(intersection)} requested KPI(s): {', '.join(intersection)}")
            elif not requested_kpi_ids and asset_kpi_ids:
                kpi_score = 0.3  # Asset has KPIs, intent had none specific
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
                    "structural_reasons": structural_reasons,
                    "kpi_reasons": kpi_reasons,
                    "semantic_reasons": semantic_reasons,
                    "mapped_kpi_count": len(asset_kpi_ids),
                },
            )
            duplicate_candidates.append(candidate_obj)

        duplicate_candidates.sort(key=lambda x: x.similarity_score, reverse=True)

        high_sim_duplicates = [c for c in duplicate_candidates if c.similarity_score >= self.DUPLICATE_THRESHOLD]
        has_duplicates = len(high_sim_duplicates) > 0
        top_cand = duplicate_candidates[0] if duplicate_candidates else None
        top_score = top_cand.similarity_score if top_cand else 0.0

        explanation = (
            f"Found {len(high_sim_duplicates)} high-confidence duplicate asset(s) (similarity >= {self.DUPLICATE_THRESHOLD}). "
            f"Top match: {top_cand.asset_id} ('{top_cand.asset_name}') with composite similarity {top_score:.2f}."
            if has_duplicates
            else "No high-confidence duplicates detected. Existing assets have distinct structural scope or KPI mappings."
        )

        logger.info(f"[{self.agent_name}] {explanation}")
        return DuplicationResult(
            has_duplicates=has_duplicates,
            candidates=duplicate_candidates[:8],
            highest_similarity_score=top_score,
            primary_duplicate_asset_id=top_cand.asset_id if (top_cand and has_duplicates) else None,
            explanation=explanation,
        )

