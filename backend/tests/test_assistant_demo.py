import pytest
from backend.app.db.session import SessionLocal
from backend.app.agents.orchestrator import orchestrator


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_official_nubeqa_demo_request(db):
    """
    Validation test for the exact Bayer challenge prompt:
    'I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country.'
    Verifies that the multi-agent system extracts real dataset entities, uncovers existing Nubeqa assets,
    reconciles canonical KPIs, evaluates duplication, and produces an evidence-backed decision.
    """
    prompt = "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."
    response = orchestrator.process_request(prompt, db)

    # 1. Intent Verification
    intent = response.intent
    assert "Nubeqa" in intent.products
    assert "Global" in intent.markets
    assert "revenue growth" in intent.kpis
    assert "market access" in intent.kpis
    assert "country" in intent.dimensions

    # 2. Existing Discovery Verification
    discovery = response.discovery
    assert len(discovery.exact_matches) > 0
    # Assets found should be Nubeqa assets in the database
    matched_ids = [m.asset_id for m in discovery.exact_matches]
    assert any("AST-" in aid for aid in matched_ids)

    # 3. KPI Intelligence Alignment
    kpis = response.kpi_analysis
    # Revenue growth -> KPI-004 Net Sales Growth
    # Market access -> KPI-027 Market Access Coverage
    assert "KPI-004" in kpis.canonical_approved_kpi_ids
    assert "KPI-027" in kpis.canonical_approved_kpi_ids

    # 4. Duplication Analysis
    dup = response.duplication
    assert len(dup.candidates) > 0

    # 5. Governance Evaluation
    gov = response.governance
    assert "RULE-001" in gov.applicable_rule_ids or "RULE-002" in gov.applicable_rule_ids

    # 6. Recommendation Verification
    rec = response.recommendation
    assert rec.decision in ["REUSE", "CONSOLIDATE", "MODIFY"]
    assert rec.confidence >= 0.75
    assert len(rec.primary_recommendation) > 10
    assert len(rec.rationale) > 20

    # 7. Trace Completeness
    assert len(response.traces) == 6
    for t in response.traces:
        assert t.status == "success"
        assert t.duration_ms >= 0.0

