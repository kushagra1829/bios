import pytest
from backend.app.db.session import SessionLocal
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    KpiAnalysisResult,
    DuplicationResult,
    GovernanceAgentResult,
    DecisionType,
    MatchTier,
)
from backend.app.agents.specialists import (
    IntentAgent,
    DiscoveryAgent,
    KpiIntelligenceAgent,
    DuplicationAgent,
    GovernanceAgent,
    DecisionAgent,
)


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_intent_agent_extraction():
    agent = IntentAgent()
    prompt = "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."
    intent = agent.process(prompt)

    assert "Nubeqa" in intent.products
    assert "Global" in intent.markets
    assert "revenue growth" in intent.kpis
    assert "market access" in intent.kpis
    assert "country" in intent.dimensions
    assert intent.confidence >= 0.7


def test_intent_agent_missing_requirements():
    agent = IntentAgent()
    # Ambiguous prompt lacking product and market
    prompt = "I want a dashboard showing some numbers."
    intent = agent.process(prompt)

    assert len(intent.products) == 0
    assert len(intent.missing_or_ambiguous) >= 2
    assert intent.confidence < 0.7


def test_intent_agent_empty_prompt():
    agent = IntentAgent()
    intent = agent.process("")
    assert intent.confidence == 0.0
    assert len(intent.missing_or_ambiguous) > 0


def test_discovery_agent(db_session):
    agent = DiscoveryAgent()
    intent = BusinessIntent(
        raw_prompt="Test Nubeqa",
        products=["Nubeqa"],
        markets=["Global"],
        kpis=["revenue growth"],
        dimensions=["country"],
        time_periods=["monthly"],
        business_purpose="Test",
        missing_or_ambiguous=[],
        confidence=1.0,
    )
    result = agent.process(intent, db_session)

    assert result.total_searched == 360
    assert len(result.exact_matches) > 0
    # Every exact match must be Nubeqa
    for match in result.exact_matches:
        assert match.match_tier == MatchTier.EXACT
        assert "Nubeqa" in match.product_scope


def test_kpi_intelligence_agent(db_session):
    agent = KpiIntelligenceAgent()
    intent = BusinessIntent(
        raw_prompt="Test KPIs",
        products=["Nubeqa"],
        markets=["Global"],
        kpis=["revenue growth", "market access", "Net Sales Local", "non_existent_metric"],
        dimensions=[],
        time_periods=[],
        business_purpose="Test",
        missing_or_ambiguous=[],
        confidence=1.0,
    )
    result = agent.process(intent, db_session)

    # revenue growth maps to canonical KPI-004
    # market access maps to canonical KPI-027
    assert "KPI-004" in result.canonical_approved_kpi_ids
    assert "KPI-027" in result.canonical_approved_kpi_ids

    # Net Sales Local is unapproved/conflicted KPI-002
    assert "KPI-002" in result.unapproved_or_conflicted_kpi_ids

    # non_existent_metric is unmatched
    assert "non_existent_metric" in result.unmatched_requested_metrics
    assert result.has_conflicts is True


def test_duplication_agent_weighting(db_session):
    agent = DuplicationAgent()
    discovery_agent = DiscoveryAgent()
    kpi_agent = KpiIntelligenceAgent()

    intent = BusinessIntent(
        raw_prompt="Nubeqa Global",
        products=["Nubeqa"],
        markets=["Global"],
        kpis=["Net Sales Growth"],
        dimensions=["country"],
        time_periods=["monthly"],
        business_purpose="Sales tracking",
        missing_or_ambiguous=[],
        confidence=1.0,
    )
    discovery = discovery_agent.process(intent, db_session)
    kpis = kpi_agent.process(intent, db_session)

    result = agent.process(intent, discovery, kpis, db_session)

    assert isinstance(result, DuplicationResult)
    assert len(result.candidates) > 0
    top = result.candidates[0]
    # Structural and KPI scores must be non-negative floats <= 1.0
    assert 0.0 <= top.structural_similarity <= 1.0
    assert 0.0 <= top.kpi_similarity <= 1.0
    assert 0.0 <= top.semantic_similarity <= 1.0


def test_governance_agent_active_findings_integration(db_session):
    agent = GovernanceAgent()
    discovery_agent = DiscoveryAgent()
    kpi_agent = KpiIntelligenceAgent()
    dup_agent = DuplicationAgent()

    intent = BusinessIntent(
        raw_prompt="Nubeqa Global",
        products=["Nubeqa"],
        markets=["Global"],
        kpis=["Net Sales Local"],
        dimensions=[],
        time_periods=[],
        business_purpose="Test",
        missing_or_ambiguous=[],
        confidence=1.0,
    )
    discovery = discovery_agent.process(intent, db_session)
    kpis = kpi_agent.process(intent, db_session)
    dup = dup_agent.process(intent, discovery, kpis, db_session)

    result = agent.process(intent, discovery, kpis, dup, db_session)

    assert isinstance(result, GovernanceAgentResult)
    assert "RULE-002" in result.applicable_rule_ids
    assert result.human_approval_required is True


def test_decision_agent_clarification(db_session):
    agent = DecisionAgent()
    # Incomplete intent
    ambiguous_intent = BusinessIntent(
        raw_prompt="vague",
        products=[],
        markets=[],
        kpis=[],
        dimensions=[],
        time_periods=[],
        business_purpose="unclear",
        missing_or_ambiguous=["Product missing", "Market missing", "KPI missing"],
        confidence=0.3,
    )
    decision = agent.process(
        intent=ambiguous_intent,
        discovery=DiscoveryResult(),
        kpi_analysis=KpiAnalysisResult(),
        duplication=DuplicationResult(),
        governance=GovernanceAgentResult(),
        db=db_session,
    )

    assert decision.decision == DecisionType.NEEDS_CLARIFICATION
    assert len(decision.next_steps) > 0

