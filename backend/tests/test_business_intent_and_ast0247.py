"""
Regression Test Suite for Business Intent Routing and AST-0247 Recommendation Integrity.

Covers:
1. "Nubeqa sales in France in 2026" -> BUSINESS_DATA_QUESTION & DATA_ANSWER
2. "What were Nubeqa sales in Germany in Q1 2026?" -> BUSINESS_DATA_QUESTION & DATA_ANSWER
3. "Find a certified Nubeqa sales dashboard in France" -> ASSET_REQUEST & ASSET_RECOMMENDATION / MODIFY (not AST-0247 reuse)
4. "Create a new Nubeqa sales dashboard" -> ASSET_REQUEST & ASSET_RECOMMENDATION
5. "Show Nubeqa sales in France and recommend an existing dashboard" -> COMBINED INTENT (BUSINESS_DATA_QUESTION + ASSET_REQUEST)
6. Integrity safeguard: AST-0247 cannot be recommended as a healthy reuse target solely because it is promoted
   when its lifecycle status is 'candidate_retire'.
"""

import pytest
from backend.app.db.session import SessionLocal
from backend.app.agents.request_router import classify
from backend.app.agents.schemas import RequestType, DecisionType
from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.agents.answering.eligibility import check_target
from backend.app.models.core import AnalyticsAssets


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_classify_nubeqa_sales_france_2026():
    """Business data questions without asset nouns must classify as BUSINESS_DATA_QUESTION."""
    res = classify("Nubeqa sales in France in 2026")
    assert res.request_types == [RequestType.BUSINESS_DATA_QUESTION]


def test_classify_nubeqa_sales_germany_q1_2026():
    """Specific period data questions must classify as BUSINESS_DATA_QUESTION."""
    res = classify("What were Nubeqa sales in Germany in Q1 2026?")
    assert res.request_types == [RequestType.BUSINESS_DATA_QUESTION]


def test_classify_find_certified_nubeqa_dashboard_france():
    """Requests asking to find an existing dashboard must classify as ASSET_REQUEST."""
    res = classify("Find a certified Nubeqa sales dashboard in France")
    assert res.request_types == [RequestType.ASSET_REQUEST]


def test_classify_create_new_nubeqa_dashboard():
    """Requests to build/create an asset must classify as ASSET_REQUEST."""
    res = classify("Create a new Nubeqa sales dashboard")
    assert res.request_types == [RequestType.ASSET_REQUEST]


def test_classify_show_sales_and_recommend_dashboard_combined():
    """Requests asking for data figures AND a dashboard recommendation must have COMBINED INTENT."""
    res = classify("Show Nubeqa sales in France and recommend an existing dashboard")
    assert RequestType.BUSINESS_DATA_QUESTION in res.request_types
    assert RequestType.ASSET_REQUEST in res.request_types
    # Data question is primary to answer the numbers first
    assert res.primary == RequestType.BUSINESS_DATA_QUESTION


def test_e2e_nubeqa_sales_france_2026_response(db):
    """
    Verify end-to-end response for 'Nubeqa sales in France in 2026':
    - Returns calculated sales value (€194.84M) and currency (M EUR)
    - States covered period (Jan–Oct 2026)
    - Notes synthetic data composition (actual-like vs forecast-like)
    - Renders as DATA_ANSWER and DecisionType.INFORMATIONAL
    """
    orchestrator = AgentOrchestrator()
    resp = orchestrator.process_request("Nubeqa sales in France in 2026", db)

    # 1. Classification & Decision Type
    assert RequestType.BUSINESS_DATA_QUESTION in resp.request_types
    assert resp.recommendation.decision == DecisionType.INFORMATIONAL

    # 2. Data answer presence
    assert resp.data_answer is not None
    assert resp.data_answer.status in ("ANSWERED", "PARTIAL")

    # 3. Calculated figures integrity (10 months in dataset sum to 194.84 M EUR)
    net_sales_fig = next((f for f in resp.data_answer.figures if "net sales" in f.label.lower()), None)
    assert net_sales_fig is not None
    assert net_sales_fig.value == 194.84
    assert net_sales_fig.unit == "M EUR"

    # 4. Covered reporting period and caveats
    assert resp.data_answer.coverage.dataset_period == "Jan–Oct 2026"
    assert "actual_like_synthetic" in resp.data_answer.coverage.value_type_counts
    assert "forecast_like_synthetic" in resp.data_answer.coverage.value_type_counts

    # 5. Presentation format
    assert resp.presentation is not None
    assert resp.presentation.response_type == "DATA_ANSWER"
    assert "€194.84M" in resp.presentation.direct_answer


def test_e2e_nubeqa_sales_germany_q1_2026_response(db):
    """Verify end-to-end response for 'What were Nubeqa sales in Germany in Q1 2026?'."""
    orchestrator = AgentOrchestrator()
    resp = orchestrator.process_request("What were Nubeqa sales in Germany in Q1 2026?", db)

    assert RequestType.BUSINESS_DATA_QUESTION in resp.request_types
    assert resp.recommendation.decision == DecisionType.INFORMATIONAL
    assert resp.presentation is not None
    assert resp.presentation.response_type == "DATA_ANSWER"
    assert "€59.52M" in resp.presentation.direct_answer


def test_ast0247_ineligible_for_reuse_due_to_candidate_retire(db):
    """
    Regression test ensuring AST-0247 cannot be recommended as a healthy reuse target
    solely because it is promoted when its lifecycle status indicates candidate retirement.
    """
    asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == "AST-0247").first()
    assert asset is not None
    assert asset.endorsement == "promoted"
    assert asset.lifecycle_status == "candidate_retire"

    # Direct eligibility check must fail for REUSE
    check = check_target(db, "AST-0247", "REUSE")
    assert check.eligible is False
    assert any("candidate_retire" in r or "RULE-008" in r for r in check.reasons)

    # Workflow test: Asking to find certified Nubeqa dashboard in France must NOT recommend AST-0247 for reuse
    orchestrator = AgentOrchestrator()
    resp = orchestrator.process_request("Find a certified Nubeqa sales dashboard in France", db)

    # Must NOT recommend reuse of AST-0247
    if resp.recommendation.decision == DecisionType.REUSE:
        assert "AST-0247" not in resp.recommendation.target_asset_ids

    # If AST-0247 was evaluated, it must appear in ineligible_targets
    ineligible_ids = [t.get("asset_id") for t in resp.recommendation.ineligible_targets]
    assert "AST-0247" in ineligible_ids or "AST-0247" not in resp.recommendation.target_asset_ids

