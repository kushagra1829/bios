import logging
from typing import List, Optional, Set, Dict, Any
from sqlalchemy.orm import Session

from backend.app.agents.answering.governance_answers import GovernanceQuestionAnswerer
from backend.app.agents.answering.migration_answers import MigrationQuestionAnswerer
from backend.app.agents.entity_catalog import expand_market_scope
from backend.app.agents.request_router import title_has_topic
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    DiscoveredAsset,
    MatchTier,
    RequestType,
)
from backend.app.models.core import AnalyticsAssets, SemanticModels, Owners
from backend.app.models.governance import AssetKpiMap

logger = logging.getLogger(__name__)


class DiscoveryAgent:
    """
    Specialist Agent 2: Analytics Discovery.
    Systematically inspects the enterprise BI catalog (AnalyticsAssets, SemanticModels, Workspaces)
    to discover existing assets that satisfy the user's analytical requirements.
    Classifies matched assets into EXACT, PARTIAL, and WEAK match tiers with exact source evidence.
    
    Enterprise Capabilities:
      - Evaluates product scope, market scope, and title keyword alignment.
      - Distinguishes exact scope matches from partial matches.
      - Enriches candidates with verified physical evidence (model_id, owner_id, lifecycle_status).
      - Clearly identifies missing evidence (unassigned owner, unindexed model) and negative evidence.
      - Never invents asset IDs, ownership, or lineage.
    """

    agent_name = "DiscoveryAgent"

    def process(self, intent: BusinessIntent, db: Session) -> DiscoveryResult:
        logger.info(f"[{self.agent_name}] Searching catalog for products={intent.products}, markets={intent.markets}")

        # Query all active or candidate assets with their underlying semantic models and owners
        query = (
            db.query(AnalyticsAssets, SemanticModels, Owners)
            .outerjoin(SemanticModels, AnalyticsAssets.model_id == SemanticModels.model_id)
            .outerjoin(Owners, AnalyticsAssets.owner_id == Owners.owner_id)
        )
        all_records = query.all()

        exact_matches: List[DiscoveredAsset] = []
        partial_matches: List[DiscoveredAsset] = []
        weak_candidates: List[DiscoveredAsset] = []

        products_lower = {p.lower() for p in intent.products}
        markets_lower = expand_market_scope(intent.markets, db)
        kpis_lower = {k.lower() for k in intent.kpis}

        for asset, model, owner in all_records:
            asset_prod = (asset.product_scope or "").lower()
            asset_mkt = (asset.market_scope or "").lower()
            asset_name_lower = asset.asset_name.lower()

            prod_match = any(p in asset_prod or p in asset_name_lower for p in products_lower) if products_lower else False
            mkt_match = asset_mkt in markets_lower

            # Check keyword / KPI match in asset title (words > 3 chars to avoid noise)
            kpi_title_matches = [
                k for k in kpis_lower
                if any(term in asset_name_lower for term in k.split() if len(term) > 3)
            ]

            reasons: List[str] = []
            missing_evidence: List[str] = []
            negative_evidence: List[str] = []
            score = 0.0

            if prod_match:
                score += 0.5
                reasons.append(f"Product scope matches '{asset.product_scope}'")
            elif products_lower and asset_prod:
                # Explicit product scope mismatch
                negative_evidence.append(f"Product scope '{asset.product_scope}' does not match requested '{', '.join(intent.products)}'")

            if mkt_match:
                score += 0.3
                reasons.append(f"Market scope aligns with '{asset.market_scope}'")

            if kpi_title_matches:
                score += 0.2
                reasons.append(f"Title keywords match requested concepts: {', '.join(kpi_title_matches)}")

            if asset.endorsement in ("certified", "promoted"):
                score += 0.1
                reasons.append(f"Endorsement level is '{asset.endorsement}'")

            # Document missing vs negative evidence
            if not owner or not asset.owner_id:
                missing_evidence.append("No active owner assigned (RULE-004 accountability defect)")
            elif owner.status != "active":
                negative_evidence.append(f"Assigned owner is '{owner.status}'")

            if not model:
                missing_evidence.append("Underlying semantic model not found")

            if asset.lifecycle_status != "active":
                negative_evidence.append(f"Lifecycle status is '{asset.lifecycle_status}'")

            score = min(1.0, round(score, 2))
            topic_match = [t for t in intent.title_topics if title_has_topic(asset.asset_name, t)]
            named_in_request = asset.asset_id in intent.asset_ids_mentioned
            if topic_match:
                reasons.append(f"Title carries the requested topic: {', '.join(topic_match)}")
            if named_in_request:
                reasons.insert(0, "Named in the request")

            # Structure Discovered Asset with Full Evidence
            discovered = DiscoveredAsset(
                asset_id=asset.asset_id,
                asset_name=asset.asset_name,
                match_tier=MatchTier.WEAK,
                product_scope=asset.product_scope,
                market_scope=asset.market_scope,
                platform=asset.platform,
                endorsement=asset.endorsement,
                lifecycle_status=asset.lifecycle_status,
                match_score=score,
                match_reasons=reasons,
                model_id=model.model_id if model else None,
                model_name=model.model_name if model else None,
                model_endorsement=model.endorsement if model else None,
                owner_name=owner.owner_name if owner else None,
                estimated_audience=asset.estimated_audience,
                evidence={
                    "asset_id": asset.asset_id,
                    "workspace_id": asset.workspace_id,
                    "model_id": asset.model_id,
                    "product_scope": asset.product_scope,
                    "market_scope": asset.market_scope,
                    "endorsement": asset.endorsement,
                    "lifecycle_status": asset.lifecycle_status,
                    "owner_status": owner.status if owner else "missing",
                    "missing_evidence": missing_evidence,
                    "negative_evidence": negative_evidence,
                    "title_topic_match": topic_match,
                    "named_in_request": named_in_request,
                },
            )

            # Match Tier Assignment:
            # An asset the request names by ID is the subject of the request, whatever its scope.
            if named_in_request:
                discovered.match_tier = MatchTier.EXACT
                discovered.match_score = max(discovered.match_score, 0.7)
                exact_matches.append(discovered)
            # EXACT: Both product and market match, high alignment score (>= 0.7)
            elif prod_match and mkt_match and score >= 0.7:
                discovered.match_tier = MatchTier.EXACT
                exact_matches.append(discovered)
            # PARTIAL: Product matches OR (market matches AND title matches requested KPIs)
            elif prod_match or (mkt_match and kpi_title_matches):
                discovered.match_tier = MatchTier.PARTIAL
                partial_matches.append(discovered)
            # WEAK: Moderate score
            elif score >= 0.3:
                discovered.match_tier = MatchTier.WEAK
                weak_candidates.append(discovered)

        # Sort tiers by score descending; an asset named in the request always comes first.
        exact_matches.sort(key=lambda x: (x.evidence.get("named_in_request", False), x.match_score), reverse=True)
        partial_matches.sort(key=lambda x: x.match_score, reverse=True)
        weak_candidates.sort(key=lambda x: x.match_score, reverse=True)

        notes = (
            f"Searched {len(all_records)} assets. Found {len(exact_matches)} exact matches, "
            f"{len(partial_matches)} partial matches, and {len(weak_candidates)} weak candidates."
        )

        # Title-topic matches ("Budget Mgmt") are kept even when they rank below the top ten partials.
        topic_ids = [a.asset_id for a in exact_matches + partial_matches if a.evidence.get("title_topic_match")]
        if intent.title_topics:
            topical = [a for a in partial_matches if a.evidence.get("title_topic_match")]
            partial_matches = topical + [a for a in partial_matches if not a.evidence.get("title_topic_match")]
            notes += f" Title topics requested: {', '.join(intent.title_topics)} ({len(topic_ids)} matching asset(s))."

        result = DiscoveryResult(
            exact_matches=exact_matches[:10],
            partial_matches=partial_matches[:10],
            weak_candidates=weak_candidates[:10],
            total_searched=len(all_records),
            search_notes=notes,
            title_topic_matches=topic_ids,
        )
        self._retrieve_answers(intent, db, result)
        logger.info(f"[{self.agent_name}] {result.search_notes}")
        return result

    @staticmethod
    def _retrieve_answers(intent: BusinessIntent, db: Session, result: DiscoveryResult) -> None:
        """
        Data, governance and migration questions are answered from source records here, so the
        Decision Agent decides with the evidence and never turns a question into an asset action.
        """
        from backend.app.analytics.data_query import DataQueryEngine
        types = set(intent.request_types)
        if RequestType.DATA_QUESTION in types or RequestType.BUSINESS_DATA_QUESTION in types:
            result.data_answer = DataQueryEngine().answer(intent.raw_prompt, intent, db)
            result.search_notes += f" Data question answered from Product_Market_Monthly ({result.data_answer.status})."
        if RequestType.GOVERNANCE_QUESTION in types:
            result.governance_answer = GovernanceQuestionAnswerer().answer(intent.raw_prompt, intent, db)
            result.search_notes += f" Governance records retrieved ({result.governance_answer.question_kind})."
        if RequestType.MIGRATION_QUESTION in types:
            result.migration_answer = MigrationQuestionAnswerer().answer(intent.raw_prompt, intent, db)
            result.search_notes += f" Migration backlog retrieved ({result.migration_answer.total_matching} record(s))."
