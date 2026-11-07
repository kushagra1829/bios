"""
Milestone 5.5.2: Europe stays the requested scope and resolves only through Markets.region.
Synthetic catalogs exercise classifications the current workbook doesn't contain.
"""
import json
import re
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from backend.app.agents.adapters import DeterministicFallbackAdapter, OllamaAdapter
from backend.app.agents.entity_catalog import EntityCatalog, KpiEntry, load_entity_catalog
from backend.app.agents.intent_resolution import normalize_intent, parse_intent
from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.agents.schemas import (
    DecisionType,
    GeographyStatus,
    IntentExtraction,
    KpiMapping,
)
from backend.app.agents.specialists import (
    DecisionAgent,
    DiscoveryAgent,
    DuplicationAgent,
    GovernanceAgent,
    IntentAgent,
    KpiIntelligenceAgent,
)
from backend.app.db.session import SessionLocal
from backend.app.models.assistant import AssistantRequests
from backend.app.models.core import AnalyticsAssets
from backend.app.models.domain import Markets
from backend.app.models.governance import AssetKpiMap, GovernanceFindings

MODEL = "qwen3.5:4b"
EUROPE_REQUEST = "Nubeqa sales in Europe, monthly"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def catalog(db):
    return load_entity_catalog(db)


def synthetic(*markets):
    return EntityCatalog(
        products=(("P-NUB", "Nubeqa"),),
        product_scopes=(),
        markets=tuple(markets),
        market_scopes=("Global",),
        kpis=(KpiEntry("KPI-001", "Net Sales", True),),
    )


FI_EUROPE = ("FI", "Finland", "Europe")
SE_EUROPE = ("SE", "Sweden", "Northern Europe")
DE_EMEA = ("DE", "Germany", "EMEA")
FR_NONE = ("FR", "France", None)
ES_BLANK = ("ES", "Spain", "  ")
US_NA = ("US", "United States", "North America")
JP_APAC = ("JP", "Japan", "Asia Pacific")


def resolve(prompt, catalog):
    return normalize_intent(prompt, parse_intent(prompt, catalog), None, catalog)


def phrase_for(intent, original):
    return next(p for p in intent.geography.phrases if p.original_phrase == original)


# ---------------------------------------------------------------------- Europe


def test_europe_with_verified_markets_resolves_to_exactly_those():
    intent = resolve(EUROPE_REQUEST, synthetic(FI_EUROPE, SE_EUROPE, US_NA, JP_APAC))

    assert intent.markets == ["FI", "SE"]
    assert intent.geography.status == GeographyStatus.RESOLVED
    assert intent.geography.resolved_market_ids == ["FI", "SE"]
    assert intent.geography.unresolved_geography == []
    phrase = phrase_for(intent, "Europe")
    assert phrase.normalized_scope == "Europe"
    assert "verifies FI, SE" in phrase.explanation
    assert intent.raw_prompt == EUROPE_REQUEST


def test_europe_with_only_emea_classification_needs_clarification():
    intent = resolve(EUROPE_REQUEST, synthetic(DE_EMEA, US_NA))

    assert intent.markets == []
    assert intent.geography.status == GeographyStatus.NEEDS_CLARIFICATION
    assert intent.geography.resolved_market_ids == []
    assert intent.geography.unresolved_geography == ["Europe"]
    phrase = phrase_for(intent, "Europe")
    assert phrase.normalized_scope == "Europe"
    assert phrase.suggested_market_ids == ["DE"]
    assert "broader than Europe" in phrase.explanation
    assert "Europe, the Middle East and Africa" in phrase.explanation


def test_europe_with_incomplete_metadata_is_partially_resolved():
    intent = resolve(EUROPE_REQUEST, synthetic(FI_EUROPE, DE_EMEA, FR_NONE, ES_BLANK, US_NA))

    assert intent.markets == ["FI"]
    assert intent.geography.status == GeographyStatus.PARTIALLY_RESOLVED
    assert intent.geography.resolved_market_ids == ["FI"]
    assert intent.geography.unresolved_geography == ["Europe"]
    phrase = phrase_for(intent, "Europe")
    assert phrase.suggested_market_ids == ["DE", "FR", "ES"]
    assert "FR, ES have no region recorded" in phrase.explanation
    assert any("DE only as EMEA" in m for m in intent.missing_or_ambiguous)


def test_europe_with_only_unclassified_markets_invents_no_classification():
    intent = resolve(EUROPE_REQUEST, synthetic(FR_NONE, US_NA))

    assert intent.markets == []
    assert intent.geography.status == GeographyStatus.NEEDS_CLARIFICATION
    assert phrase_for(intent, "Europe").suggested_market_ids == ["FR"]


def test_europe_with_no_related_markets_offers_no_candidates():
    intent = resolve(EUROPE_REQUEST, synthetic(US_NA, JP_APAC))

    assert intent.markets == []
    assert phrase_for(intent, "Europe").suggested_market_ids == []
    assert "No market in the catalog is classified as European" in intent.geography.explanation


def test_classification_comes_from_data_not_from_country_names():
    """The same country flips with its recorded region, proving nothing is hardcoded."""
    assert resolve(EUROPE_REQUEST, synthetic(("DE", "Germany", "Europe"))).markets == ["DE"]
    assert resolve(EUROPE_REQUEST, synthetic(("DE", "Germany", "EMEA"))).markets == []
    assert resolve(EUROPE_REQUEST, synthetic(("DE", "Germany", None))).markets == []
    assert resolve(EUROPE_REQUEST, synthetic(("JP", "Japan", "Europe"))).markets == ["JP"]


@pytest.mark.parametrize("phrase", ["Europe", "europe", "EUROPE", "European"])
def test_original_phrase_is_preserved_and_scope_is_normalized(catalog, phrase):
    intent = resolve(f"Nubeqa sales in {phrase}, monthly", catalog)
    assert phrase_for(intent, phrase).normalized_scope == "Europe"
    assert "EMEA" not in intent.markets


def test_qualified_europe_is_not_read_as_all_of_europe():
    intent = resolve("Nubeqa sales in Western Europe", synthetic(FI_EUROPE, DE_EMEA))
    phrase = phrase_for(intent, "Western Europe")
    assert phrase.normalized_scope == "Western Europe"
    assert phrase.status == GeographyStatus.NEEDS_CLARIFICATION
    assert intent.markets == []


def test_qualified_phrase_that_is_a_catalog_region_resolves_as_that_region():
    intent = resolve("Nubeqa sales in Northern Europe", synthetic(SE_EUROPE, FI_EUROPE))
    assert intent.markets == ["Northern Europe"]
    assert intent.geography.resolved_market_ids == ["SE"]


def test_explicit_market_alongside_unresolved_europe_is_partial(catalog):
    intent = resolve("Nubeqa sales in Finland and Europe, monthly", catalog)
    assert intent.markets == ["FI"]
    assert intent.geography.status == GeographyStatus.PARTIALLY_RESOLVED
    assert intent.geography.unresolved_geography == ["Europe"]


# ---------------------------------------------------------------------- Never rewritten to EMEA


@pytest.mark.parametrize(
    "prompt",
    [
        "Nubeqa sales in Europe.",
        "European Nubeqa sales",
        "Compare Nubeqa across Europe by country, monthly",
        "Nubeqa net sales for Europe and EMEA are separate questions: only Europe please",
    ],
)
def test_europe_is_never_silently_rewritten_to_emea(catalog, prompt):
    intent = resolve(prompt, catalog)
    if "EMEA" not in prompt:
        assert "EMEA" not in intent.markets
        assert "EMEA" not in intent.geography.resolved_market_ids
    assert any(p.normalized_scope == "Europe" for p in intent.geography.phrases)


def test_no_europe_alias_exists_in_the_catalog(catalog):
    assert catalog.canonical_market("Europe") is None
    assert "europe" not in catalog.geography_terms()


def test_current_workbook_markets_are_not_classified_as_european(db, catalog):
    """Documents the data this fix relies on: the workbook records EMEA, never Europe."""
    regions = {m.region for m in db.query(Markets).all()}
    assert "EMEA" in regions
    assert not any(re.search("europ", region, re.IGNORECASE) for region in regions)

    intent = resolve(EUROPE_REQUEST, catalog)
    assert intent.geography.status == GeographyStatus.NEEDS_CLARIFICATION
    assert set(phrase_for(intent, "Europe").suggested_market_ids) == {
        m.market_id for m in db.query(Markets).filter_by(region="EMEA").all()
    }


def test_no_source_file_classifies_a_country_as_european():
    agents = Path(__file__).resolve().parents[1] / "app" / "agents"
    for name in ("entity_catalog.py", "intent_resolution.py"):
        source = (agents / name).read_text(encoding="utf-8")
        assert not re.search(r"EUROPEAN_(MARKETS|COUNTRIES)", source)
        assert not re.search(r"[\"'](?:DE|FR|FI|SE|IT|ES|UK)[\"']\s*[,:].*[Ee]urop", source)


def test_llm_cannot_substitute_emea_for_europe(catalog):
    baseline = parse_intent(EUROPE_REQUEST, catalog)
    proposal = IntentExtraction(
        products=["Nubeqa"],
        markets=["EMEA", "Europe", "DE"],
        kpi_mappings=[],
        unmapped_metrics=[],
        dimensions=[],
        time_periods=[],
        business_purpose="Track Nubeqa sales in EMEA.",
    )
    intent = normalize_intent(EUROPE_REQUEST, baseline, proposal, catalog)

    assert intent.markets == []
    rejected = {d.proposed for d in intent.resolution.rejected}
    assert {"EMEA", "DE", "Track Nubeqa sales in EMEA."} <= rejected
    assert "Europe" in {d.proposed for d in intent.resolution.confirmed}


# ---------------------------------------------------------------------- Other geography


def test_emea_explicitly_requested_resolves_to_its_markets(db, catalog):
    intent = resolve("Nubeqa sales in EMEA", catalog)
    assert intent.markets == ["EMEA"]
    assert intent.geography.status == GeographyStatus.RESOLVED
    assert set(intent.geography.resolved_market_ids) == {
        m.market_id for m in db.query(Markets).filter_by(region="EMEA").all()
    }
    assert not any(p.normalized_scope == "Europe" for p in intent.geography.phrases)


@pytest.mark.parametrize(
    "prompt,market,surface",
    [
        ("Nubeqa sales in Finland", "FI", "Finland"),
        ("Nubeqa sales in China", "CN", "China"),
        ("Nubeqa sales in the US", "US", "US"),
        ("Nubeqa FI sales", "FI", "FI"),
    ],
)
def test_explicit_market_is_preserved(catalog, prompt, market, surface):
    intent = resolve(prompt, catalog)
    assert intent.markets == [market]
    assert intent.geography.status == GeographyStatus.RESOLVED
    phrase = phrase_for(intent, surface)
    assert (phrase.normalized_scope, phrase.resolved_market_ids) == (market, [market])


def test_fi_and_us_together(catalog):
    intent = resolve("Compare FI and US.", catalog)
    assert intent.markets == ["FI", "US"]
    assert intent.geography.resolved_market_ids == ["FI", "US"]
    assert intent.geography.status == GeographyStatus.RESOLVED


@pytest.mark.parametrize(
    "prompt,term",
    [("Nubeqa sales in us", "us"), ("Nubeqa sales in America", "America")],
)
def test_ambiguous_geography_needs_clarification(db, catalog, prompt, term):
    intent = resolve(prompt, catalog)
    assert intent.markets == []
    assert intent.geography.status == GeographyStatus.NEEDS_CLARIFICATION
    assert intent.geography.unresolved_geography == [term]


@pytest.mark.parametrize("prompt", ["Nubeqa sales dashboard", "Nubeqa dashboard by country", "Show us the sales."])
def test_no_geographic_scope(catalog, prompt):
    intent = resolve(prompt, catalog)
    assert intent.markets == []
    assert intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert intent.geography.phrases == []
    assert any("market is unspecified" in m for m in intent.missing_or_ambiguous)


def test_global_scope_is_resolved(catalog):
    intent = resolve("Global Nubeqa sales", catalog)
    assert intent.markets == ["Global"]
    assert intent.geography.status == GeographyStatus.RESOLVED
    assert intent.geography.resolved_market_ids == ["Global"]


# ---------------------------------------------------------------------- Through the agents


def deterministic_orchestrator(intent_agent=None, decision_agent=None):
    adapter = DeterministicFallbackAdapter()
    return AgentOrchestrator(
        intent_agent=intent_agent or IntentAgent(adapter),
        kpi_agent=KpiIntelligenceAgent(adapter),
        decision_agent=decision_agent or DecisionAgent(adapter),
    )


def test_europe_request_gets_clarification_not_a_decision_over_all_markets(db):
    response = deterministic_orchestrator().process_request(EUROPE_REQUEST, db)

    recommendation = response.recommendation
    assert recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert recommendation.target_asset_ids == []
    assert "broader than Europe" in recommendation.rationale
    assert recommendation.next_steps[0].startswith("Confirm the geographic scope for: Europe.")
    assert response.intent.confidence >= 0.45


def test_explicit_emea_request_still_reaches_a_decision(db):
    response = deterministic_orchestrator().process_request("Nubeqa sales in EMEA, monthly", db)
    assert response.recommendation.decision != DecisionType.NEEDS_CLARIFICATION
    assert {a.market_scope for a in response.discovery.exact_matches} <= {"DE", "ES", "FI", "FR", "IT", "SE", "UK"}


def test_no_geography_still_reaches_a_decision_as_before(db):
    response = deterministic_orchestrator().process_request("Monthly Nubeqa net sales dashboard", db)
    assert response.intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert response.recommendation.decision != DecisionType.NEEDS_CLARIFICATION


def test_resolved_markets_reach_all_agents_when_europe_is_partial(db):
    """Verified European markets flow through; the unverified one doesn't, and a warning says so."""
    catalog = synthetic(FI_EUROPE, DE_EMEA)
    intent = resolve(EUROPE_REQUEST, catalog)
    seen = {}

    class FixedIntentAgent:
        def process(self, prompt, db=None):
            seen["intent"] = intent
            return intent

    def spying(agent_cls, name):
        class Spy(agent_cls):
            def process(self, received, *args, **kwargs):
                seen[name] = received
                return super().process(received, *args, **kwargs)

        return Spy

    adapter = DeterministicFallbackAdapter()
    response = AgentOrchestrator(
        intent_agent=FixedIntentAgent(),
        discovery_agent=spying(DiscoveryAgent, "discovery")(),
        kpi_agent=spying(KpiIntelligenceAgent, "kpi")(adapter),
        duplication_agent=spying(DuplicationAgent, "duplication")(),
        governance_agent=spying(GovernanceAgent, "governance")(),
        decision_agent=spying(DecisionAgent, "decision")(adapter),
    ).process_request(EUROPE_REQUEST, db)

    assert set(seen) == {"intent", "discovery", "kpi", "duplication", "governance", "decision"}
    assert all(received is intent for received in seen.values())
    assert response.discovery.exact_matches
    assert {a.market_scope for a in response.discovery.exact_matches} == {"FI"}
    # The unverified market could change the candidates, so no definitive action is issued.
    assert response.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert response.recommendation.target_asset_ids == []
    assert "DE only as EMEA" in response.recommendation.rationale
    assert "Already resolved: FI" in response.recommendation.next_steps[0]


# ---------------------------------------------------------------------- Final review scenarios


@pytest.mark.parametrize(
    "prompt,markets,status,resolved,unresolved",
    [
        ("Sales in US", ["US"], GeographyStatus.RESOLVED, ["US"], []),
        ("Sales in America", [], GeographyStatus.NEEDS_CLARIFICATION, [], ["America"]),
        ("IT budget dashboard", [], GeographyStatus.NOT_SPECIFIED, [], []),
        ("Sales in Finland", ["FI"], GeographyStatus.RESOLVED, ["FI"], []),
        ("Sales in Finland and Europe", ["FI"], GeographyStatus.PARTIALLY_RESOLVED, ["FI"], ["Europe"]),
        ("Sales in Europe", [], GeographyStatus.NEEDS_CLARIFICATION, [], ["Europe"]),
        ("Sales in EMEA", ["EMEA"], GeographyStatus.RESOLVED, ["DE", "ES", "FI", "FR", "IT", "SE", "UK"], []),
    ],
)
def test_review_scenarios(catalog, prompt, markets, status, resolved, unresolved):
    intent = resolve(prompt, catalog)
    assert intent.markets == markets
    assert intent.geography.status == status
    assert intent.geography.resolved_market_ids == resolved
    assert intent.geography.unresolved_geography == unresolved


def test_no_geography_is_not_treated_as_ambiguous(db, catalog):
    prompt = "Monthly Nubeqa net sales dashboard"
    intent = resolve(prompt, catalog)
    assert intent.ambiguities == []
    assert intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert intent.geography.unresolved_geography == []

    response = deterministic_orchestrator().process_request(prompt, db)
    assert response.recommendation.decision != DecisionType.NEEDS_CLARIFICATION
    assert response.recommendation.target_asset_ids


def test_america_follows_catalog_evidence_and_is_never_a_silent_country():
    both = resolve("Sales in America", synthetic(US_NA, ("CA", "Canada", "North America")))
    assert both.markets == []
    assert phrase_for(both, "America").suggested_market_ids == ["US", "North America"]

    # With no North America region in the catalog, it still doesn't become the US.
    only_us = resolve("Sales in America", synthetic(("US", "United States", "Americas")))
    assert only_us.markets == []
    assert only_us.geography.status == GeographyStatus.NEEDS_CLARIFICATION

    neither = resolve("Sales in America", synthetic(JP_APAC))
    assert neither.markets == []
    assert neither.geography.unresolved_geography == ["America"]


@pytest.mark.parametrize(
    "prompt",
    [
        "Nubeqa sales in Finland and Europe, monthly",
        "Xarelto net sales in the US and America, monthly",
    ],
)
def test_partial_scope_gives_no_definitive_action_even_when_otherwise_complete(db, prompt):
    """These have a product, KPI and time period, so only the geography rule can stop them."""
    response = deterministic_orchestrator().process_request(prompt, db)

    assert len(response.intent.missing_or_ambiguous) < 3
    assert response.intent.geography.status == GeographyStatus.PARTIALLY_RESOLVED
    assert response.intent.markets
    recommendation = response.recommendation
    assert recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert recommendation.target_asset_ids == [] and recommendation.target_model_ids == []
    assert recommendation.alternatives == []


def test_llm_cannot_add_a_kpi_from_words_inside_a_longer_matched_kpi(catalog):
    """Found by live inference: this flipped CONSOLIDATE to MODIFY by adding approved Net Sales."""
    prompt = "Nubeqa Net Sales Local monthly global"
    proposal = IntentExtraction(
        products=[],
        markets=[],
        kpi_mappings=[KpiMapping(requested_phrase="Net Sales", catalog_kpi_name="Net Sales")],
        unmapped_metrics=[],
        dimensions=[],
        time_periods=[],
        business_purpose="",
    )
    intent = normalize_intent(prompt, parse_intent(prompt, catalog), proposal, catalog)

    assert intent.kpis == ["net sales local"]
    assert "part of 'net sales local'" in intent.resolution.rejected[0].reason


# ---------------------------------------------------------------------- Geography represents geography only


@pytest.mark.parametrize(
    "prompt,term",
    [
        ("IT budget dashboard", "IT"),
        ("Budget dashboard for IT", "IT"),
        ("Show US the sales", "US"),
    ],
)
def test_possible_abbreviation_without_geographic_evidence_is_not_geography(catalog, prompt, term):
    intent = resolve(prompt, catalog)

    assert intent.markets == []
    assert intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert intent.geography.phrases == []
    assert intent.geography.unresolved_geography == []
    # The open question is kept, but separately from geography.
    assert [(a.category, a.term) for a in intent.ambiguities] == [("term", term)]


def test_it_budget_dashboard_clarification_comes_from_other_fields(db):
    response = deterministic_orchestrator().process_request("IT budget dashboard", db)
    assert response.intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert response.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert response.recommendation.target_asset_ids == []
    joined = " ".join(response.recommendation.next_steps)
    assert "Confirm whether 'IT' refers to market IT." in joined
    assert "brand/product" in joined
    assert "Confirm the geographic scope" not in joined


def test_unclear_term_blocks_a_definitive_action_on_an_otherwise_complete_request(db):
    response = deterministic_orchestrator().process_request("Monthly Nubeqa net sales dashboard for IT", db)
    assert response.intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert response.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert response.recommendation.target_asset_ids == []


def test_it_with_geographic_evidence_still_resolves_to_italy(catalog):
    for prompt in ("Sales in IT", "IT market performance", "Compare IT and DE"):
        assert "IT" in resolve(prompt, catalog).markets


def test_pronoun_never_records_an_ambiguity_or_geography(catalog):
    intent = resolve("Build a dashboard for us.", catalog)
    assert intent.geography.status == GeographyStatus.NOT_SPECIFIED
    assert intent.ambiguities == []


# ---------------------------------------------------------------------- Requests with no product


def _mapped_kpis(db, asset_id):
    return {m.kpi_id for m in db.query(AssetKpiMap).filter_by(asset_id=asset_id).all()}


def test_sales_in_us_does_not_assume_a_product(db):
    response = deterministic_orchestrator().process_request("Sales in US", db)

    # The evidence behind this decision: the only title match is Nubeqa's, with no KPI mapping.
    asset = db.query(AnalyticsAssets).filter_by(asset_id="AST-0132").one()
    assert asset.product_scope == "Nubeqa" and asset.market_scope == "US"
    assert "KPI-001" not in _mapped_kpis(db, "AST-0132")

    recommendation = response.recommendation
    assert recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert recommendation.target_asset_ids == []
    assert "would assume a product" in recommendation.rationale
    assert "AST-0132 'Nubeqa Net Sales' (Nubeqa)" in recommendation.rationale
    assert any("brand/product" in step for step in recommendation.next_steps)
    assert any("AST-0132" in step for step in recommendation.next_steps)


def test_title_word_inside_another_metric_is_not_evidence(db):
    """'net' in 'Gross-to-Net' once selected a Hyrnuo asset for a net sales request."""
    recommendation = deterministic_orchestrator().process_request("Monthly net sales in the US", db).recommendation
    assert recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert "AST-0082" not in recommendation.target_asset_ids


def test_generic_request_with_portfolio_evidence_is_not_blocked(db):
    """Not an arbitrary block: a portfolio asset answers a request that names no product."""
    response = deterministic_orchestrator().process_request("Sales in Finland", db)
    recommendation = response.recommendation

    asset = db.query(AnalyticsAssets).filter_by(asset_id="AST-0022").one()
    assert asset.product_scope == "All Pharma" and asset.market_scope == "FI" and asset.lifecycle_status == "active"
    assert recommendation.decision == DecisionType.MODIFY
    assert recommendation.target_asset_ids == ["AST-0022"]
    assert recommendation.human_approval_required is True


def test_title_only_evidence_is_disclosed_and_lowers_confidence(db):
    recommendation = deterministic_orchestrator().process_request("Sales in Finland", db).recommendation

    assert "KPI-001" not in _mapped_kpis(db, "AST-0022")
    assert recommendation.confidence == 0.6
    assert "doesn't confirm" in recommendation.rationale
    assert "rather than assuming one" in recommendation.rationale
    assert any("Verify that AST-0022 calculates Net Sales (KPI-001)" in step for step in recommendation.next_steps)


def test_regional_request_discloses_the_narrower_target_scope(db):
    recommendation = deterministic_orchestrator().process_request("Sales in EMEA", db).recommendation
    assert recommendation.target_asset_ids == ["AST-0022"]
    assert "scoped to FI, within the requested EMEA" in recommendation.rationale


def test_no_product_or_market_does_not_justify_build_new(db):
    recommendation = deterministic_orchestrator().process_request("Monthly net sales dashboard", db).recommendation
    assert recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert "no scope to search" in recommendation.rationale


def test_genuine_gap_with_a_market_can_still_build_new(db):
    recommendation = deterministic_orchestrator().process_request(
        "New monthly Certified Asset Share dashboard for Japan", db
    ).recommendation
    assert recommendation.decision == DecisionType.BUILD_NEW


def test_named_product_path_is_unchanged(db):
    recommendation = deterministic_orchestrator().process_request("Monthly Lynkuet net sales dashboard in Finland.", db).recommendation
    assert recommendation.decision == DecisionType.MODIFY
    assert recommendation.target_asset_ids == ["AST-0336"]


# ---------------------------------------------------------------------- Repository setup


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_env_example_default_database_needs_no_extra_driver():
    values = dotenv_values(REPO_ROOT / ".env.example")
    assert "DATABASE_URL" not in values, "SQLite is the default, so no other database may be active"
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "requirements-postgres.txt" in example


def test_postgres_driver_is_optional_and_documented():
    assert "psycopg" not in (REPO_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "psycopg" in (REPO_ROOT / "backend" / "requirements-postgres.txt").read_text(encoding="utf-8")
    assert "requirements-postgres.txt" in (REPO_ROOT / "docs" / "DEVELOPMENT_SETUP.md").read_text(encoding="utf-8")


def test_data_docs_carry_provenance_and_no_compliance_claim():
    for name in ("DATA_DICTIONARY.md", "DATA_QUALITY_REPORT.md"):
        text = (REPO_ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "created by SinceAI, not Bayer" in text
        assert not re.search(r"HIPAA|GDPR", text)
    assert "bayer-synthetic.com" not in (REPO_ROOT / "docs" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    assert "created by SinceAI, not Bayer" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- Candidate transparency


def test_emea_markets_are_suggestions_and_never_verified_matches(catalog):
    phrase = phrase_for(resolve(EUROPE_REQUEST, catalog), "Europe")

    assert phrase.resolved_market_ids == []
    assert phrase.suggested_market_ids == ["DE", "ES", "FI", "FR", "IT", "SE", "UK"]
    assert "suggestions only, not verified matches" in phrase.explanation
    assert "need your confirmation" in phrase.explanation


def test_catalog_facts_are_separated_from_general_knowledge(catalog):
    phrase = phrase_for(resolve(EUROPE_REQUEST, catalog), "Europe")

    assert "No Markets.region value names Europe." in phrase.catalog_evidence
    assert any("only as EMEA" in fact for fact in phrase.catalog_evidence)
    assert not any("Middle East" in fact for fact in phrase.catalog_evidence)
    assert any("Middle East" in note and "not a catalog fact" in note for note in phrase.external_context)
    assert "general knowledge, not a catalog fact" in phrase.explanation


def test_explanation_never_claims_candidates_are_european(catalog):
    explanation = phrase_for(resolve(EUROPE_REQUEST, catalog), "Europe").explanation
    assert "verifies no market as European" in explanation
    for market in ("DE", "ES", "FI", "FR", "IT", "SE", "UK"):
        assert not re.search(rf"\b{market}\b[^.]*\bare (?:all )?European\b", explanation)


def test_clarification_labels_suggestions_for_the_user(db):
    recommendation = deterministic_orchestrator().process_request(EUROPE_REQUEST, db).recommendation
    assert "Suggestions to confirm, not verified matches: DE, ES, FI, FR, IT, SE, UK." in recommendation.next_steps[0]


# ---------------------------------------------------------------------- Clarification quality


def test_next_steps_do_not_ask_for_what_is_already_resolved(db):
    steps = deterministic_orchestrator().process_request(EUROPE_REQUEST, db).recommendation.next_steps
    joined = " ".join(steps).lower()
    assert "brand/product" not in joined
    assert "metric" not in joined
    assert "time frequency" not in joined
    assert len(steps) == 1


def test_next_steps_ask_for_what_is_missing(db):
    steps = deterministic_orchestrator().process_request("Sales in Europe", db).recommendation.next_steps
    joined = " ".join(steps)
    assert "brand/product" in joined
    assert "time frequency" in joined
    assert "metric" not in joined


def test_rationale_has_no_doubled_punctuation(db):
    recommendation = deterministic_orchestrator().process_request(EUROPE_REQUEST, db).recommendation
    assert ".." not in recommendation.rationale


# ---------------------------------------------------------------------- Recommendation isolation


def _asset_market(db, asset_id):
    return db.query(AnalyticsAssets).filter_by(asset_id=asset_id).one().market_scope


def test_findings_outside_unresolved_scope_are_not_blockers(db):
    response = deterministic_orchestrator().process_request(EUROPE_REQUEST, db)
    governance = response.governance

    assert governance.out_of_scope_finding_ids, "this scenario needs out-of-scope findings to mean anything"
    assert governance.request_finding_ids == []
    assert response.recommendation.blockers == []
    assert not any(re.search(r"AST-\d+", w) for w in response.recommendation.warnings)
    assert response.recommendation.out_of_scope_warnings == governance.out_of_scope_warnings
    assert "aren't blockers for this request" in response.recommendation.rationale


def test_all_findings_stay_visible_and_are_classified_once(db):
    governance = deterministic_orchestrator().process_request(EUROPE_REQUEST, db).governance
    assert set(governance.active_finding_ids) == set(governance.request_finding_ids) | set(governance.out_of_scope_finding_ids)
    assert not set(governance.request_finding_ids) & set(governance.out_of_scope_finding_ids)
    scopes = {r["finding_id"]: r["scope"] for r in governance.evidence_references if "finding_id" in r}
    assert all(scopes[f] == "outside_request" for f in governance.out_of_scope_finding_ids)


def test_requested_kpi_blocker_still_applies_with_unresolved_geography(db):
    """An unapproved KPI the user asked for concerns the request itself, whatever the geography."""
    response = deterministic_orchestrator().process_request("Nubeqa Net Sales Local in Europe, monthly", db)
    assert response.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert any("RULE-002 BLOCKER: Requested KPI KPI-002" in b for b in response.recommendation.blockers)


def test_blockers_on_a_resolved_market_only_name_in_scope_or_target_assets(db):
    response = deterministic_orchestrator().process_request("Quarterly Gross-to-Net Rate for Beyonttra in Finland", db)
    targets = set(response.recommendation.target_asset_ids)
    for blocker in response.recommendation.blockers:
        for asset_id in re.findall(r"AST-\d+", blocker):
            assert asset_id in targets or _asset_market(db, asset_id) == "FI"


def test_finding_on_the_recommended_target_still_blocks(db):
    """The target is a direct dependency, even when it sits outside the requested market."""
    response = deterministic_orchestrator().process_request(
        "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country.", db
    )
    target = response.recommendation.target_asset_ids[0]
    target_findings = db.query(GovernanceFindings).filter(
        GovernanceFindings.target_entity_id == target, GovernanceFindings.status.in_(["open", "persisting"])
    ).all()
    candidate_ids = {a.asset_id for a in response.discovery.exact_matches + response.discovery.partial_matches[:5]}
    if target in candidate_ids:
        assert {f.finding_id for f in target_findings} <= set(response.governance.request_finding_ids)
    assert response.recommendation.blockers == response.governance.blockers
    assert any("RULE-003 BLOCKER" in b for b in response.recommendation.blockers)


def test_no_geography_keeps_product_wide_governance_scope(db):
    response = deterministic_orchestrator().process_request("Monthly Nubeqa net sales dashboard", db)
    assert response.governance.request_finding_ids
    assert response.governance.out_of_scope_finding_ids == []


def test_narrative_facts_exclude_out_of_scope_warnings(db):
    captured = {}

    def handler(request):
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        title = body["format"]["title"]
        if title == "IntentExtraction":
            payload = {
                "products": [], "markets": [], "kpi_mappings": [], "unmapped_metrics": [],
                "dimensions": [], "time_periods": [], "business_purpose": "",
            }
        elif title == "KpiReviewOutput":
            payload = {"reviews": []}
        else:
            facts = json.loads(body["messages"][-1]["content"].split("Context (JSON):\n", 1)[1])
            captured.update(facts)
            payload = {
                "decision_echo": facts["decision"],
                "human_approval_required_echo": facts["human_approval_required"],
                "blocker_count_echo": facts["blocker_count"],
                "summary": "Please confirm the markets.",
            }
        return httpx.Response(200, json={"model": MODEL, "message": {"content": json.dumps(payload)}})

    adapter = OllamaAdapter(model=MODEL, max_retries=0, transport=httpx.MockTransport(handler))
    response = AgentOrchestrator(
        intent_agent=IntentAgent(adapter),
        kpi_agent=KpiIntelligenceAgent(adapter),
        decision_agent=DecisionAgent(adapter),
    ).process_request(EUROPE_REQUEST, db)

    assert response.recommendation.out_of_scope_warnings
    assert captured["blocker_count"] == 0
    assert captured["blockers"] == []
    assert "out_of_scope_warnings" not in captured
    assert not re.search(r"AST-\d+", json.dumps(captured))


def test_geography_decision_is_recorded_with_the_request(db):
    response = deterministic_orchestrator().process_request(EUROPE_REQUEST, db)

    stored = json.loads(db.query(AssistantRequests).filter_by(request_id=response.request_id).one().parsed_intent_json)
    assert stored["raw_prompt"] == EUROPE_REQUEST
    assert stored["markets"] == []
    assert stored["geography"]["status"] == "NEEDS_CLARIFICATION"
    assert stored["geography"]["phrases"][0]["original_phrase"] == "Europe"
    assert stored["geography"]["phrases"][0]["normalized_scope"] == "Europe"
    assert "broader than Europe" in stored["geography"]["explanation"]
    trace_input = json.loads(next(t for t in response.traces if t.agent_name == "DiscoveryAgent").input_json)
    assert trace_input["geography"]["status"] == "NEEDS_CLARIFICATION"


def test_provider_doesn_t_change_the_europe_outcome(db):
    def handler(request):
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        title = body["format"]["title"]
        if title == "IntentExtraction":
            payload = {
                "products": ["Nubeqa"],
                "markets": ["EMEA", "DE"],
                "kpi_mappings": [],
                "unmapped_metrics": [],
                "dimensions": [],
                "time_periods": ["monthly"],
                "business_purpose": "Track Nubeqa sales across EMEA.",
            }
        elif title == "KpiReviewOutput":
            payload = {"reviews": []}
        else:
            facts = json.loads(body["messages"][-1]["content"].split("Context (JSON):\n", 1)[1])
            payload = {
                "decision_echo": facts["decision"],
                "human_approval_required_echo": facts["human_approval_required"],
                "blocker_count_echo": facts["blocker_count"],
                "summary": "Please confirm the markets.",
            }
        return httpx.Response(200, json={"model": MODEL, "message": {"content": json.dumps(payload)}})

    adapter = OllamaAdapter(model=MODEL, max_retries=0, transport=httpx.MockTransport(handler))
    assisted = AgentOrchestrator(
        intent_agent=IntentAgent(adapter),
        kpi_agent=KpiIntelligenceAgent(adapter),
        decision_agent=DecisionAgent(adapter),
    ).process_request(EUROPE_REQUEST, db)
    deterministic = deterministic_orchestrator().process_request(EUROPE_REQUEST, db)

    assert assisted.intent.markets == deterministic.intent.markets == []
    assert assisted.recommendation.decision == deterministic.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert assisted.intent.geography == deterministic.intent.geography
