"""
Final AI Intelligence Transformation: routing, data answers, reuse-before-build, governance
consistency, deduplicated findings, approvals, unsupported/ambiguous handling and response structure.

Expected numbers are computed here from the source workbook with openpyxl, independently of the
BIOS data engine.
"""
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.app.agents.adapters import DeterministicFallbackAdapter
from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.agents.request_router import classify
from backend.app.agents.schemas import ActionStatus, DecisionType, RequestType
from backend.app.db.session import SessionLocal
from backend.app.main import app

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "data" / "source" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def pmm():
    wb = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    rows = list(wb["Product_Market_Monthly"].iter_rows(values_only=True))
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def run(prompt, db):
    from backend.app.agents.specialists.intent_agent import IntentAgent
    from backend.app.agents.specialists.decision_agent import DecisionAgent

    return AgentOrchestrator(
        intent_agent=IntentAgent(adapter=DeterministicFallbackAdapter()),
        decision_agent=DecisionAgent(adapter=DeterministicFallbackAdapter()),
    ).process_request(prompt, db)


def total(pmm, product_id, market_id, months, field="net_sales_m_eur_syn"):
    return round(sum(r[field] for r in pmm if r["product_id"] == product_id and r["market_id"] == market_id
                     and r["month"].strftime("%Y-%m") in months), 2)


# ------------------------------------------------------------------ intent routing
@pytest.mark.parametrize("prompt,expected", [
    ("What were Nubeqa sales in Germany in Q1 2026?", [RequestType.DATA_QUESTION]),
    ("Show monthly sales trends for Nubeqa.", [RequestType.DATA_QUESTION]),
    ("I need a Nubeqa sales dashboard for Germany.", [RequestType.ASSET_REQUEST]),
    ("Build a scoreboard for European sales.", [RequestType.ASSET_REQUEST]),
    ("Why is AST-0268 blocked?", [RequestType.GOVERNANCE_QUESTION]),
    ("Which reports use non-canonical KPIs?", [RequestType.GOVERNANCE_QUESTION]),
    ("Which Tableau dashboards should be migrated?", [RequestType.MIGRATION_QUESTION]),
    ("Which reports can be retired?", [RequestType.MIGRATION_QUESTION]),
    ("Check Nubeqa sales and tell me whether we need a new dashboard.", [RequestType.DATA_QUESTION, RequestType.ASSET_REQUEST]),
    ("Sales in Finland", [RequestType.ASSET_REQUEST]),  # terse intake phrasing keeps the asset contract
])
def test_request_routing(prompt, expected):
    assert classify(prompt).request_types == expected


def test_routing_is_deterministic():
    prompt = "Compare Nubeqa and other products in Germany."
    assert classify(prompt).request_types == classify(prompt).request_types == [RequestType.DATA_QUESTION]


# ------------------------------------------------------------------ data question vs asset request
def test_data_question_is_answered_not_consolidated(db):
    res = run("Check Nubeqa sales in Germany for 2024–2025.", db)
    assert res.recommendation.decision == DecisionType.INFORMATIONAL
    assert res.data_answer.status == "NO_DATA"
    assert all(f.value is None for f in res.data_answer.figures)
    assert "Jan–Oct 2026" in res.data_answer.headline
    assert res.presentation.response_type == "DATA_ANSWER"


def test_numbers_match_independent_workbook_calculation(db, pmm):
    res = run("What were Nubeqa sales in Germany in Q1 2026?", db)
    expected = total(pmm, "P-NUB", "DE", {"2026-01", "2026-02", "2026-03"})
    assert res.data_answer.status == "ANSWERED"
    assert res.data_answer.figures[0].value == pytest.approx(expected, abs=0.01)
    assert res.data_answer.unit == "M EUR"
    assert res.data_answer.coverage.records_used == 3
    assert res.data_answer.source["sheet"] == "Product_Market_Monthly"


def test_forecast_vs_actual_is_independently_correct(db, pmm):
    res = run("Show Xarelto forecast versus actual in United States in Q2 2026.", db)
    months = {"2026-04", "2026-05", "2026-06"}
    net = total(pmm, "P-XAR", "US", months)
    fc = total(pmm, "P-XAR", "US", months, "forecast_m_eur_syn")
    values = [f.value for f in res.data_answer.figures]
    assert values[0] == pytest.approx(net, abs=0.01) and values[1] == pytest.approx(fc, abs=0.01)
    assert values[2] == pytest.approx(net - fc, abs=0.011)


def test_partial_period_is_disclosed(db):
    res = run("What were Nubeqa sales in Germany in 2026?", db)
    assert res.data_answer.status == "PARTIAL"
    assert "2026-11" in res.data_answer.coverage.months_missing_in_requested_range


def test_combined_request_answers_data_and_assesses_asset(db):
    res = run("What were Xarelto net sales in the US in Q1 2026, and do we need a new dashboard for it?", db)
    assert res.request_types[:2] == [RequestType.DATA_QUESTION, RequestType.ASSET_REQUEST]
    assert res.data_answer.status == "ANSWERED"
    assert res.recommendation.decision != DecisionType.INFORMATIONAL


# ------------------------------------------------------------------ geography boundaries
def test_europe_is_never_emea(db):
    res = run("Show Nubeqa sales in Europe.", db)
    assert res.data_answer.status == "NEEDS_CLARIFICATION"
    assert res.data_answer.figures == []
    assert res.recommendation.decision == DecisionType.NEEDS_CLARIFICATION


def test_region_expands_to_catalog_members(db):
    res = run("What were Kerendia net sales in EMEA in Q1 2026?", db)
    assert sorted(res.data_answer.markets) == ["DE", "ES", "FI", "FR", "IT", "SE", "UK"]


# ------------------------------------------------------------------ KPI resolution
@pytest.mark.parametrize("prompt,field", [
    ("How many units of Xarelto were shipped in Japan in Q2 2026?", "units_shipped_syn"),
    ("What was the average OTIF for Eylea in Germany in Q1 2026?", "otif_pct_syn"),
    ("What was the average market access coverage for Nubeqa in France in H1 2026?", "market_access_coverage_pct_syn"),
])
def test_measure_resolution(db, prompt, field):
    assert run(prompt, db).data_answer.measure_field == field


def test_kpi_definition_reports_catalog_status(db):
    res = run("Is Net Sales Local an approved KPI?", db)
    assert res.governance_answer.question_kind == "KPI_DEFINITION"
    assert "KPI-002" in res.governance_answer.headline and "NOT the canonical" in res.governance_answer.headline


# ------------------------------------------------------------------ reuse before build, governance blockers
def test_unowned_asset_is_never_a_target(db):
    res = run("I need a scoreboard for Nubeqa sales in Germany.", db)
    assert "AST-0268" not in res.recommendation.target_asset_ids
    assert any(t["asset_id"] == "AST-0268" for t in res.recommendation.ineligible_targets)
    assert res.recommendation.decision != DecisionType.BUILD_NEW


def test_modifying_unowned_asset_is_blocked(db):
    res = run("Add forecast variance to AST-0268.", db)
    assert res.recommendation.decision == DecisionType.MODIFY
    assert res.recommendation.action_status == ActionStatus.BLOCKED
    assert res.recommendation.target_asset_ids == []
    assert res.presentation.governance.blockers[0].rule_id == "RULE-003"


def test_policy_request_on_unowned_asset_is_blocked(db):
    res = run("Build a dashboard using an asset with no accountable owner.", db)
    assert res.recommendation.action_status == ActionStatus.BLOCKED
    assert any("RULE-003" in b for b in res.recommendation.blockers)


def test_title_similarity_alone_does_not_consolidate(db):
    res = run("We already have three similar Nubeqa dashboards. What should we do?", db)
    assert res.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert not res.duplication.consolidation_eligible_pairs
    assert res.duplication.title_alike_groups


def test_gate_backed_consolidation(db):
    res = run("Are there duplicate Hyrnuo reports in the US that we should consolidate?", db)
    assert res.recommendation.decision == DecisionType.CONSOLIDATE
    assert set(res.recommendation.target_asset_ids) <= {"AST-0056", "AST-0147"}
    assert res.recommendation.human_approval_required is True


def test_phantom_asset_is_not_acted_on_or_echoed(db):
    res = run("Consolidate existing German analytics into non-existent phantom asset AST-9999.", db)
    assert res.recommendation.decision == DecisionType.NEEDS_CLARIFICATION
    assert "AST-9999" not in res.recommendation.model_dump_json()


# ------------------------------------------------------------------ deduplicated findings
def test_findings_are_deduplicated_with_backend_counts_kept(db):
    res = run("Add forecast variance to AST-0268.", db)
    gov = res.presentation.governance
    keys = [(b.rule_id, b.asset_id, b.message) for b in gov.blockers]
    assert len(keys) == len(set(keys))
    assert gov.backend_blocker_count == len(res.recommendation.blockers)
    assert gov.displayed_blocker_count <= gov.backend_blocker_count


# ------------------------------------------------------------------ human approval
@pytest.mark.parametrize("prompt", [
    "Retire AST-0268 now.",
    "What is the migration path for AST-0065?",
    "I need a scoreboard for Nubeqa sales in Germany.",
])
def test_consequential_actions_require_approval(db, prompt):
    rec = run(prompt, db).recommendation
    if rec.decision in (DecisionType.MODIFY, DecisionType.CONSOLIDATE, DecisionType.MIGRATE, DecisionType.RETIRE, DecisionType.BUILD_NEW):
        assert rec.human_approval_required is True


def test_retiring_unowned_asset_is_blocked(db):
    rec = run("Retire AST-0268 now.", db).recommendation
    assert rec.decision == DecisionType.RETIRE and rec.action_status == ActionStatus.BLOCKED


# ------------------------------------------------------------------ unsupported and ambiguous
@pytest.mark.parametrize("prompt", [
    "What is Kerendia market share in France?",
    "What were Stivarga sales in Germany?",
    "What was the profit margin for Xarelto in Japan?",
])
def test_unsupported_requests_produce_no_figures(db, prompt):
    res = run(prompt, db)
    assert res.data_answer.status == "UNSUPPORTED"
    assert res.data_answer.figures == []


def test_year_over_year_without_prior_year(db):
    assert run("What was the year-over-year sales change?", db).data_answer.status == "NO_DATA"


# ------------------------------------------------------------------ governance and migration answers
def test_why_blocked_explains_rule_003(db):
    res = run("Why is AST-0268 blocked?", db)
    assert res.recommendation.decision == DecisionType.INFORMATIONAL
    assert "RULE-003" in res.governance_answer.headline


def test_migration_answer_uses_backlog(db):
    res = run("Which Nubeqa dashboards should be migrated to Power BI?", db)
    groups = res.migration_answer.groups
    assert set(groups) <= {"MIGRATE", "CONSOLIDATE_BEFORE_MIGRATION", "REBUILD_ON_SHARED_MODEL", "RETIRE", "HUMAN_REVIEW"}
    assert res.migration_answer.total_matching == 8


# ------------------------------------------------------------------ response structure through the API
def test_api_response_structure_governance_last():
    client = TestClient(app)
    body = client.post("/api/v1/assistant/requests", json={"prompt": "I need a scoreboard for Nubeqa sales in Germany."}).json()
    pres = body["presentation"]
    assert list(pres)[-1] == "governance"
    for key in ("recommended_action", "action_status", "direct_answer", "why", "next_steps", "governance"):
        assert key in pres
    assert len(body["traces"]) == 6
    assert body["request_types"] == ["ASSET_REQUEST"]
