from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from backend.app.models.core import AnalyticsAssets, LineageEdges
from backend.app.models.governance import AssetKpiMap, KpiCatalog


class DuplicateGateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    METRIC_DRIFT = "METRIC_DRIFT"


@dataclass
class DuplicateGateEvaluation:
    pair: Tuple[str, str]
    g1_scope_pass: bool
    g2_canonical_group_jaccard: float
    g3_exact_kpi_jaccard: float
    g4_shares_model: bool
    layers_used: List[str]
    consolidation_eligible: bool
    recommendation: str
    explanation: str


class DuplicateGateEngine:
    """
    Enterprise Duplicate Validation Gates G1–G4.
    Validates candidate similarity versus proven functional duplication:
      - Gate G1 (Scope Compatibility): Product and market scope must be compatible.
      - Gate G2 (Canonical Concept Group Overlap): Evaluates Jaccard of canonical metric concepts.
      - Gate G3 (Exact Metric Drift): Evaluates exact KPI overlap. Disjoint mapped KPIs indicate metric drift -> route to RULE-002.
      - Gate G4 (Structural Lineage Model): Shared semantic model and lineage.
    Reports layers_used for auditable explainability.
    """

    LAYERS = [
        "scope_compatibility",
        "canonical_group_jaccard",
        "exact_kpi_jaccard",
        "structural_lineage",
    ]

    @classmethod
    def evaluate_pair(cls, db: Session, asset_id_1: str, asset_id_2: str) -> DuplicateGateEvaluation:
        a1 = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_id_1).first()
        a2 = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_id_2).first()

        if not a1 or not a2:
            raise KeyError(f"Asset pair ({asset_id_1}, {asset_id_2}) contains invalid asset ID.")

        # Gate G1: Scope Compatibility
        scope_pass = (
            a1.product_scope.lower() == a2.product_scope.lower()
            and a1.market_scope.lower() == a2.market_scope.lower()
        )

        # Mapped KPIs
        k1 = set(m.kpi_id for m in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset_id_1).all())
        k2 = set(m.kpi_id for m in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset_id_2).all())

        # Exact KPI Jaccard
        exact_kpi_jaccard = round(
            len(k1.intersection(k2)) / len(k1.union(k2)), 2
        ) if (k1 or k2) else 0.0

        # Canonical metric groups
        kpis_1 = db.query(KpiCatalog).filter(KpiCatalog.kpi_id.in_(k1)).all() if k1 else []
        kpis_2 = db.query(KpiCatalog).filter(KpiCatalog.kpi_id.in_(k2)).all() if k2 else []

        # Canonical concept name mapping: map variants to root name
        def get_concept(k: KpiCatalog) -> str:
            name = k.kpi_name.lower()
            if "net sales" in name:
                return "net_sales"
            if "inventory coverage" in name:
                return "inventory_coverage"
            if "forecast variance" in name:
                return "forecast_variance"
            if "reimbursement" in name:
                return "reimbursement_coverage"
            if "unit volume" in name or "units" in name:
                return "unit_volume"
            return name

        g1 = set(get_concept(k) for k in kpis_1)
        g2 = set(get_concept(k) for k in kpis_2)

        canonical_group_jaccard = round(
            len(g1.intersection(g2)) / len(g1.union(g2)), 2
        ) if (g1 or g2) else 0.0

        # Gate G4: Structural Model / Lineage
        shares_model = (
            (a1.model_id and a2.model_id and a1.model_id == a2.model_id)
            or (a1.workspace_id and a2.workspace_id and a1.workspace_id == a2.workspace_id)
        )

        # Consolidation & routing decision based on gates
        if not scope_pass:
            # G1 fails: Incompatible scope cannot be consolidated
            consolidation_eligible = False
            rec = "REJECT_CONSOLIDATION_SCOPE_MISMATCH"
            explanation = (
                f"Scope mismatch (Product: '{a1.product_scope}' vs '{a2.product_scope}', "
                f"Market: '{a1.market_scope}' vs '{a2.market_scope}'). Gate G1 vetoes consolidation."
            )
        elif exact_kpi_jaccard == 0.0 and canonical_group_jaccard < 0.5:
            # G3: Disjoint KPIs in same scope -> Metric Drift -> Route to RULE-002
            consolidation_eligible = False
            rec = "ROUTE_TO_RULE_002_METRIC_DRIFT"
            explanation = (
                f"Shared scope ('{a1.product_scope}', '{a1.market_scope}') but zero exact shared KPIs "
                f"and low concept similarity ({canonical_group_jaccard:.2f}). Classified as metric drift; "
                "routed to RULE-002 rather than automated consolidation."
            )
        elif canonical_group_jaccard >= 0.70:
            # G2: High canonical group similarity surfaces for review
            consolidation_eligible = True
            rec = "SURFACE_FOR_CONSOLIDATION_REVIEW"
            explanation = (
                f"High canonical concept similarity ({canonical_group_jaccard:.2f}) across shared scope "
                f"('{a1.product_scope}', '{a1.market_scope}'). Surfaced for human governance review."
            )
        else:
            consolidation_eligible = False
            rec = "INSUFFICIENT_SIMILARITY"
            explanation = f"Moderate similarity (exact: {exact_kpi_jaccard:.2f}, group: {canonical_group_jaccard:.2f}). Insufficient evidence for consolidation."

        return DuplicateGateEvaluation(
            pair=(asset_id_1, asset_id_2),
            g1_scope_pass=scope_pass,
            g2_canonical_group_jaccard=canonical_group_jaccard,
            g3_exact_kpi_jaccard=exact_kpi_jaccard,
            g4_shares_model=bool(shares_model),
            layers_used=list(cls.LAYERS),
            consolidation_eligible=consolidation_eligible,
            recommendation=rec,
            explanation=explanation,
        )

