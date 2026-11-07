import pytest
from backend.app.db.session import SessionLocal
from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.agents.schemas import AssistantWorkflowResponse
from backend.app.models.assistant import (
    AssistantRequests,
    AgentExecutionTraces,
    AssistantRecommendations,
)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_orchestration_workflow_complete(db):
    orchestrator = AgentOrchestrator()
    prompt = "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."

    response = orchestrator.process_request(prompt, db)

    assert isinstance(response, AssistantWorkflowResponse)
    assert response.status == "completed"
    assert response.request_id.startswith("REQ-")
    assert len(response.traces) == 6

    # Verify order of specialist agent execution traces
    expected_order = [
        "IntentAgent",
        "DiscoveryAgent",
        "KpiIntelligenceAgent",
        "DuplicationAgent",
        "GovernanceAgent",
        "DecisionAgent",
    ]
    for i, expected_name in enumerate(expected_order):
        trace = response.traces[i]
        assert trace.step_order == i + 1
        assert trace.agent_name == expected_name
        assert trace.status == "success"
        assert trace.duration_ms >= 0.0

    # Verify database persistence
    db_req = db.query(AssistantRequests).filter(AssistantRequests.request_id == response.request_id).first()
    assert db_req is not None
    assert db_req.status == "completed"

    db_rec = db.query(AssistantRecommendations).filter(AssistantRecommendations.request_id == response.request_id).first()
    assert db_rec is not None
    assert db_rec.decision == response.recommendation.decision.value

    db_traces = (
        db.query(AgentExecutionTraces)
        .filter(AgentExecutionTraces.request_id == response.request_id)
        .all()
    )
    assert len(db_traces) == 6


def test_orchestration_retry_mechanism(db):
    # Test retry mechanism by wrapping an agent that fails once and succeeds
    class FlakyAgent:
        def __init__(self):
            self.calls = 0

        def process(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Temporary simulated failure")
            from backend.app.agents.specialists.intent_agent import IntentAgent
            return IntentAgent().process("Nubeqa Global")

    flaky = FlakyAgent()
    orchestrator = AgentOrchestrator(intent_agent=flaky, max_retries=2)
    response = orchestrator.process_request("Nubeqa Global", db)

    assert response.status == "completed"
    assert flaky.calls == 2

