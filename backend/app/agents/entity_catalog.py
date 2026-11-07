"""
Products, markets and KPIs that intent extraction may resolve to, read from the database.

The workbook has no alias table, so the constants below are the only aliases and they are
BIOS terminology rather than catalog data. Each one is active only while its target exists
in the database, so this module can never introduce a product, market or KPI.
"""
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.app.models.core import AnalyticsAssets
from backend.app.models.domain import Markets, Products
from backend.app.models.governance import KpiCatalog

# Spelling variants of catalog markets.
MARKET_ALIASES = {
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "u.k.": "UK",
    "britain": "UK",
    "great britain": "UK",
}
REGION_ALIASES = {
    "apac": "Asia Pacific",
    "latam": "Latin America",
}
SCOPE_ALIASES = {
    "worldwide": "Global",
    "international": "Global",
}
# Terms that could mean several catalog entries. These are reported, never resolved.
AMBIGUOUS_MARKET_TERMS = {
    "america": ("US", "North America"),
}

# A market is European only when its own Markets.region says so. No country is classified here.
_EUROPEAN_REGION = re.compile(r"\beurop(?:e|ean)\b", re.IGNORECASE)
# General knowledge about what a region code stands for, not catalog data. It explains why a code
# can't replace Europe and why its markets may be worth suggesting, but it verifies nothing.
BROADER_THAN_EUROPE = {"EMEA": "Europe, the Middle East and Africa"}

# Business phrases mapped to the catalog KPI they mean.
KPI_TERMINOLOGY = {
    "revenue growth": "Net Sales Growth",
    "sales growth": "Net Sales Growth",
    "sales": "Net Sales",
    "revenue": "Net Sales",
    "forecast accuracy": "Demand Forecast Accuracy",
    "forecast bias": "Demand Forecast Bias",
    "market access": "Market Access Coverage",
    "reimbursement": "Reimbursement Status Coverage",
    "inventory": "Inventory Coverage",
    "unit volume": "Units Shipped",
    "unit volumes": "Units Shipped",
    "gross-to-net": "Gross-to-Net Rate",
}
# Metrics users ask for that have no catalog KPI. They stay in the intent so the KPI
# Intelligence Agent reports them as unmatched, instead of the request silently losing them.
UNCATALOGUED_METRICS = ("adherence", "share of voice")


@dataclass(frozen=True)
class KpiEntry:
    kpi_id: str
    name: str
    canonical_approved: bool


@dataclass(frozen=True)
class EntityCatalog:
    products: Tuple[Tuple[str, str], ...]  # (product_id, product_name)
    product_scopes: Tuple[str, ...]  # Asset scopes outside Products, such as "All Pharma"
    markets: Tuple[Tuple[str, str, Optional[str]], ...]  # (market_id, market_name, region)
    market_scopes: Tuple[str, ...]  # Asset scopes outside Markets, such as "Global"
    kpis: Tuple[KpiEntry, ...]

    @property
    def regions(self) -> Tuple[str, ...]:
        return tuple(sorted({region for _, _, region in self.markets if region and region.strip()}))

    @property
    def market_ids(self) -> Tuple[str, ...]:
        return tuple(market_id for market_id, _, _ in self.markets)

    def product_terms(self) -> Dict[str, str]:
        """Exact lowercase term -> product name."""
        terms = {scope.lower(): scope for scope in self.product_scopes}
        for product_id, name in self.products:
            terms[product_id.lower()] = name
            terms[name.lower()] = name
        return terms

    def geography_terms(self) -> Dict[str, str]:
        """
        Unambiguous multi-letter terms -> canonical value stored in the intent: a market ID,
        region name or scope. Two-letter market codes need context, so they are excluded.
        """
        terms = {scope.lower(): scope for scope in self.market_scopes}
        terms.update({region.lower(): region for region in self.regions})
        terms.update({name.lower(): market_id for market_id, name, _ in self.markets})
        for aliases, targets in (
            (MARKET_ALIASES, self.market_ids),
            (REGION_ALIASES, self.regions),
            (SCOPE_ALIASES, self.market_scopes),
        ):
            terms.update({alias: target for alias, target in aliases.items() if target in targets})
        return terms

    def canonical_market(self, term: str) -> Optional[str]:
        """Resolve a term, including a bare market code, with no context check."""
        key = term.strip().lower()
        by_id = {market_id.lower(): market_id for market_id in self.market_ids}
        return by_id.get(key) or self.geography_terms().get(key)

    def canonical_product(self, term: str) -> Optional[str]:
        return self.product_terms().get(term.strip().lower())

    def markets_in_region(self, region: str) -> List[str]:
        return [market_id for market_id, _, market_region in self.markets if market_region == region]

    def europe_classification(self) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
        """
        Sort markets by what Markets.region records about Europe. Returns the verified
        market IDs, markets in broader regions keyed by region, and markets with no region.
        """
        verified: List[str] = []
        broader: Dict[str, List[str]] = {}
        unclassified: List[str] = []
        for market_id, _, region in self.markets:
            if not region or not region.strip():
                unclassified.append(market_id)
            elif _EUROPEAN_REGION.search(region):
                verified.append(market_id)
            elif region in BROADER_THAN_EUROPE:
                broader.setdefault(region, []).append(market_id)
        return verified, broader, unclassified

    def resolve_kpi(self, term: str) -> Optional[KpiEntry]:
        """Exact catalog name or supported terminology. Canonical approved entries win on duplicate names."""
        key = term.strip().lower()
        name = KPI_TERMINOLOGY.get(key, key).lower()
        matches = [k for k in self.kpis if k.name.lower() == name]
        if not matches:
            return None
        return next((k for k in matches if k.canonical_approved), matches[0])

    @property
    def canonical_kpi_names(self) -> List[str]:
        return [k.name for k in self.kpis if k.canonical_approved]


def expand_market_scope(markets: Iterable[str], db: Session) -> Set[str]:
    """Lowercase asset market scopes a list of markets selects. A region selects its catalog markets."""
    region_markets: Dict[str, Set[str]] = {}
    for market_id, region in db.query(Markets.market_id, Markets.region).all():
        if region:
            region_markets.setdefault(region.lower(), set()).add(market_id.lower())
    scope: Set[str] = set()
    for market in markets:
        scope |= region_markets.get(market.lower(), {market.lower()})
    return scope


def load_entity_catalog(db: Session) -> EntityCatalog:
    products = tuple(
        (p.product_id, p.product_name) for p in db.query(Products).order_by(Products.product_id).all()
    )
    markets = tuple(
        (m.market_id, m.market_name, m.region) for m in db.query(Markets).order_by(Markets.market_id).all()
    )
    product_names = {name for _, name in products}
    market_ids = {market_id for market_id, _, _ in markets}
    asset_products = {row[0] for row in db.query(AnalyticsAssets.product_scope).distinct().all() if row[0]}
    asset_markets = {row[0] for row in db.query(AnalyticsAssets.market_scope).distinct().all() if row[0]}
    kpis = tuple(
        KpiEntry(
            kpi_id=k.kpi_id,
            name=k.kpi_name,
            canonical_approved=k.approval_status == "approved" and k.definition_status == "canonical",
        )
        for k in db.query(KpiCatalog).order_by(KpiCatalog.kpi_id).all()
    )
    return EntityCatalog(
        products=products,
        product_scopes=tuple(sorted(asset_products - product_names)),
        markets=markets,
        market_scopes=tuple(sorted(asset_markets - market_ids)),
        kpis=kpis,
    )


def load_default_catalog() -> EntityCatalog:
    """For callers without a session, such as IntentAgent.process(prompt)."""
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return load_entity_catalog(db)
    finally:
        db.close()
