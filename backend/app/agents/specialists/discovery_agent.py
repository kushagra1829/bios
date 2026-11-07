import logging
from typing import List, Optional, Set
from sqlalchemy.orm import Session

from backend.app.agents.entity_catalog import expand_market_scope
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    DiscoveredAsset,
    MatchTier,
)
from backend.app.models.core import AnalyticsAssets, SemanticModels, Owners

logger = logging.getLogger(__name__)


class DiscoveryAgent:
    """
    Specialist Agent 2: Analytics Discovery.
    Systematically inspects the enterprise BI catalog (AnalyticsAssets, SemanticModels, Workspaces)
    to discover existing assets that satisfy the user's analytical requirements.
    Classifies matched assets into EXACT, PARTIAL, and WEAK match tiers with exact source evidence.
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
        # Assets are scoped to a country or Global, so a region selects its catalog markets.
        markets_lower = expand_market_scope(intent.markets, db)
        kpis_lower = {k.lower() for k in intent.kpis}

        for asset, model, owner in all_records:
            asset_prod = (asset.product_scope or "").lower()
            asset_mkt = (asset.market_scope or "").lower()
            asset_name_lower = asset.asset_name.lower()

            prod_match = any(p in asset_prod or p in asset_name_lower for p in products_lower) if products_lower else False
            mkt_match = asset_mkt in markets_lower

            # Check keyword / KPI match in asset title
            kpi_title_matches = [k for k in kpis_lower if any(term in asset_name_lower for term in k.split())]

            reasons: List[str] = []
            score = 0.0

            if prod_match:
                score += 0.5
                reasons.append(f"Product scope matches '{asset.product_scope}'")
            if mkt_match:
                score += 0.3
                reasons.append(f"Market scope aligns with '{asset.market_scope}'")
            if kpi_title_matches:
                score += 0.2
                reasons.append(f"Title keywords match requested concepts: {', '.join(kpi_title_matches)}")
            if asset.endorsement in ("certified", "promoted"):
                score += 0.1
                reasons.append(f"Endorsement level is '{asset.endorsement}'")

            score = min(1.0, round(score, 2))

            # Tier assignment
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
                },
            )

            if prod_match and mkt_match and score >= 0.7:
                discovered.match_tier = MatchTier.EXACT
                exact_matches.append(discovered)
            elif prod_match or (mkt_match and kpi_title_matches):
                discovered.match_tier = MatchTier.PARTIAL
                partial_matches.append(discovered)
            elif score >= 0.3:
                discovered.match_tier = MatchTier.WEAK
                weak_candidates.append(discovered)

        # Sort tiers by score descending
        exact_matches.sort(key=lambda x: x.match_score, reverse=True)
        partial_matches.sort(key=lambda x: x.match_score, reverse=True)
        weak_candidates.sort(key=lambda x: x.match_score, reverse=True)

        notes = (
            f"Searched {len(all_records)} assets. Found {len(exact_matches)} exact matches, "
            f"{len(partial_matches)} partial matches, and {len(weak_candidates)} weak candidates."
        )

        logger.info(f"[{self.agent_name}] {notes}")
        return DiscoveryResult(
            exact_matches=exact_matches[:10],
            partial_matches=partial_matches[:10],
            weak_candidates=weak_candidates[:10],
            total_searched=len(all_records),
            search_notes=notes,
        )

