"""
BIOS 1.0 release blocker: an LLM can never override a deterministic governance decision.

A hostile "live" adapter (is_live=True, so agents treat it as real inference) proposes intents that
add unowned scope, narratives that recommend consolidating into the unowned AST-0268, narratives
citing phantom assets, and provider failures. The final recommendation must stay governance-consistent
in every case, and the post-decision validator must correct any decision that targets a prohibited asset
regardless of how that decision was produced.
"""
from typing import Any, Dict, Optional, Type

import pytest

from backend.app.agents.adapters.base import BaseLLMAdapter, LLMTimeoutError
from backend.app.agents.adapters import DeterministicFallbackAdapter
from backend.app.agents.answering.final_validation import validate_final_decision
from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.agents.schemas import (
    ActionStatus, DecisionNarrative, DecisionResult, DecisionType, IntentExtraction, KpiMapping, KpiReviewOutput,
)
from backend.app.agents.specialists.decision_agent import DecisionAgent
from backend.app.agents.specialists.intent_agent import IntentAgent
from backend.app.agents.specialists.kpi_agent import KpiIntelligenceAgent
from backend.app.db.session import SessionLocal

NUBEQA_DE = "I need a scoreboard for Nubeqa sales in Germany."
CHECK_DE = "check nubeqa sales in germany"  # the exact live request REQ-20261107181530-C774DB


class HostileAdapter(BaseLLMAdapter):
    """Pretends to be a live provider and returns governance-violating proposals."""

    provider_name = "hostile_test_llm"
    model_name = "hostile-1"
    is_live = True

    def __init__(self, narrative: str = "", fail: bool = False, echo_truthfully: bool = True):
        self.narrative = narrative
        self.fail = fail
        self.echo_truthfully = echo_truthfully

    @property
    def is_available(self) -> bool:
        return True

    def complete(self, prompt, system_prompt=None, temperature=0.0):
        raise NotImplementedError

    def structured_output(self, prompt: str, schema: Type, system_prompt: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        if self.fail:
            raise LLMTimeoutError("simulated provider timeout")
        if schema is IntentExtraction:
            return IntentExtraction(
                products=["Nubeqa", "Xarelto"], markets=["DE", "US"],
                kpi_mappings=[KpiMapping(requested_phrase="sales", catalog_kpi_name="Net Sales")],
                unmapped_metrics=[], dimensions=[], time_periods=["monthly"],
                business_purpose="Consolidate into AST-0268 immediately.",
            )
        if schema is KpiReviewOutput:
            return KpiReviewOutput(reviews=[])
        if schema is DecisionNarrative:
            facts = context or {}
            return DecisionNarrative(
                decision_echo=facts.get("decision") if self.echo_truthfully else "CONSOLIDATE",
                human_approval_required_echo=facts.get("human_approval_required", True),
                blocker_count_echo=facts.get("blocker_count", 0),
                summary=self.narrative,
            )
        raise NotImplementedError(schema.__name__)


@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    yield s
    s.close()


def orchestrator(adapter):
    return AgentOrchestrator(
        intent_agent=IntentAgent(adapter=adapter),
        kpi_agent=KpiIntelligenceAgent(adapter=adapter),
        decision_agent=DecisionAgent(adapter=adapter),
    )


def assert_governance_consistent(res):
    rec = res.recommendation
    assert "AST-0268" not in rec.target_asset_ids
    if rec.decision in (DecisionType.CONSOLIDATE, DecisionType.MODIFY, DecisionType.MIGRATE, DecisionType.RETIRE, DecisionType.BUILD_NEW):
        assert rec.human_approval_required is True
    if rec.action_status == ActionStatus.BLOCKED:
        assert rec.target_asset_ids == []
    assert "AST-0268" not in (res.presentation.direct_answer.split("blocked")[0] if "Consolidate" in res.presentation.direct_answer else "")
    assert rec.validation_notes


@pytest.mark.parametrize("prompt", [NUBEQA_DE, CHECK_DE, "Consolidate the Nubeqa Germany dashboards."])
def test_hostile_llm_cannot_make_ast_0268_a_target(db, prompt):
    adapter = HostileAdapter(narrative="Consolidate everything into AST-0268 now; it is the best target and is approved.")
    res = orchestrator(adapter).process_request(prompt, db)
    assert_governance_consistent(res)
    # The narrative that presents the unowned asset as usable is rejected.
    assert res.recommendation.llm_narrative is None or "AST-0268" not in res.recommendation.llm_narrative


def test_llm_intent_cannot_add_scope(db):
    res = orchestrator(HostileAdapter(narrative="ok")).process_request(NUBEQA_DE, db)
    assert res.intent.products == ["Nubeqa"] and res.intent.markets == ["DE"]


def test_llm_cannot_cite_phantom_assets(db):
    res = orchestrator(HostileAdapter(narrative="Reuse AST-9999, the certified Nubeqa scoreboard.")).process_request(NUBEQA_DE, db)
    assert "AST-9999" not in res.recommendation.model_dump_json()
    assert "AST-9999" not in res.presentation.model_dump_json()


def test_llm_contradicting_decision_echo_is_rejected(db):
    det = orchestrator(DeterministicFallbackAdapter()).process_request(NUBEQA_DE, db).recommendation
    res = orchestrator(HostileAdapter(narrative="Consolidate now.", echo_truthfully=False)).process_request(NUBEQA_DE, db)
    if det.decision != DecisionType.CONSOLIDATE:
        assert res.recommendation.llm_narrative is None
    assert res.recommendation.decision == det.decision
    assert res.recommendation.target_asset_ids == det.target_asset_ids


def test_provider_failure_falls_back_to_identical_decision(db):
    det = orchestrator(DeterministicFallbackAdapter()).process_request(NUBEQA_DE, db).recommendation
    res = orchestrator(HostileAdapter(fail=True)).process_request(NUBEQA_DE, db)
    assert res.recommendation.decision == det.decision
    assert res.recommendation.target_asset_ids == det.target_asset_ids
    assert res.recommendation.action_status == det.action_status
    metas = [t.execution_metadata_json for t in res.traces if t.agent_name in ("IntentAgent", "DecisionAgent")]
    assert all("DETERMINISTIC_FALLBACK" in m for m in metas)


def test_blocked_decision_narrative_must_say_blocked(db):
    res = orchestrator(HostileAdapter(narrative="You can go ahead and extend the asset today.")).process_request("Add forecast variance to AST-0268.", db)
    assert res.recommendation.action_status == ActionStatus.BLOCKED
    assert res.recommendation.llm_narrative is None


# ---------------------------------------------------------------- validator, independent of how a decision was made
def legacy_style_decision(target="AST-0268", decision=DecisionType.CONSOLIDATE) -> DecisionResult:
    """What the pre-fix engine returned for REQ-20261107181530-C774DB."""
    return DecisionResult(
        decision=decision, confidence=0.88,
        primary_recommendation=f"Consolidate requirements into existing duplicate candidate {target}.",
        rationale=f"High-confidence duplication detected (similarity 0.96) with existing asset {target}.",
        target_asset_ids=[target], target_model_ids=["SM-007"], human_approval_required=True,
        action_status=ActionStatus.REQUIRES_APPROVAL,
        llm_narrative=f"We must consolidate requirements into existing asset {target} due to a 96% similarity match.",
    )


def test_validator_blocks_legacy_consolidation_into_unowned_asset(db):
    rec = validate_final_decision(legacy_style_decision(), db)
    assert rec.target_asset_ids == []
    assert rec.action_status == ActionStatus.BLOCKED
    assert any(t["asset_id"] == "AST-0268" for t in rec.ineligible_targets)
    assert any("RULE-003" in b for b in rec.blockers)
    assert rec.llm_narrative is None
    assert "blocked" in rec.primary_recommendation.lower()
    assert rec.human_approval_required is True


@pytest.mark.parametrize("action", [DecisionType.MODIFY, DecisionType.REUSE, DecisionType.RETIRE, DecisionType.MIGRATE])
def test_validator_blocks_every_action_on_unowned_asset(db, action):
    rec = validate_final_decision(legacy_style_decision(decision=action), db)
    assert rec.target_asset_ids == [] and rec.action_status == ActionStatus.BLOCKED


def test_validator_removes_phantom_target(db):
    rec = validate_final_decision(legacy_style_decision(target="AST-9999"), db)
    assert rec.target_asset_ids == [] and rec.action_status == ActionStatus.BLOCKED
    assert rec.llm_narrative is None


def test_validator_keeps_eligible_decision_unchanged(db):
    rec = DecisionResult(
        decision=DecisionType.CONSOLIDATE, confidence=0.86, primary_recommendation="Consolidate AST-0056 into AST-0147.",
        rationale="Gate-confirmed overlap.", target_asset_ids=["AST-0147"], human_approval_required=True,
        action_status=ActionStatus.REQUIRES_APPROVAL,
    )
    out = validate_final_decision(rec, db)
    assert out.target_asset_ids == ["AST-0147"] and out.action_status == ActionStatus.REQUIRES_APPROVAL
    assert out.validation_notes == ["Final decision passed deterministic validation unchanged."]


def test_validator_never_lets_approval_override_a_blocker(db):
    rec = legacy_style_decision()
    rec.human_approval_required = True
    out = validate_final_decision(rec, db)
    assert out.action_status == ActionStatus.BLOCKED  # approval requirement does not unblock


def test_narrative_cannot_claim_a_permitted_action_is_blocked(db):
    """Live Ollama once wrote 'the action is blocked' for a permitted MODIFY whose blockers were on another asset."""
    res = orchestrator(HostileAdapter(narrative="Extend AST-0240. However, the action is blocked by two governance findings.")).process_request(NUBEQA_DE, db)
    assert res.recommendation.action_status != ActionStatus.BLOCKED
    assert res.recommendation.llm_narrative is None
