"""
Milestone 5.5 demonstration: the six BIOS agents using real local inference through Ollama.

Run from the repository root:
    backend\\.venv\\Scripts\\python.exe backend/scripts/demo_local_llm.py ["your business request"]

This script never simulates a model call. It exits non-zero when Ollama cannot serve, or
when fewer than two agents completed a real LLM-assisted execution. Everything after the
run is printed from rows read back from the database through a separate session.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx  # noqa: E402

from backend.app.agents.adapters import OllamaAdapter  # noqa: E402
from backend.app.agents.orchestrator import AgentOrchestrator  # noqa: E402
from backend.app.agents.specialists import DecisionAgent, IntentAgent, KpiIntelligenceAgent  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.models.assistant import AgentExecutionTraces, AssistantRecommendations  # noqa: E402

DEFAULT_PROMPT = (
    "I need a global Nubeqa sales dashboard showing revenue growth, forecast variance and market access by country."
)
REQUIRED_LLM_AGENTS = 2


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def print_handoff(agent_name: str, output: dict) -> None:
    """Print the facts this agent handed to the next one."""
    if agent_name == "IntentAgent":
        for key in ("products", "markets", "kpis", "dimensions", "time_periods", "business_purpose", "missing_or_ambiguous", "confidence"):
            print(f"    {key}: {output[key]}")
        for ambiguity in output["ambiguities"]:
            print(f"    ambiguous '{ambiguity['term']}': {ambiguity['reason']}")
        for note in output["interpretation_notes"]:
            print(f"    note: {note}")
        geography = output["geography"]
        print(f"    geography: {geography['status']}  resolved {geography['resolved_market_ids']}  unresolved {geography['unresolved_geography']}")
        resolution = output["resolution"]
        baseline = resolution["deterministic_intent"]
        print(f"    deterministic baseline: products={baseline['products']} markets={baseline['markets']} kpis={baseline['kpis']}")
        for status in ("accepted", "confirmed", "rejected"):
            for decision in resolution[status]:
                print(f"    LLM {status}: [{decision['category']}] {decision['proposed']}: {decision['reason']}")
    elif agent_name == "DiscoveryAgent":
        print(f"    {output['search_notes']}")
        for asset in output["exact_matches"][:3]:
            print(
                f"    DB evidence: {asset['asset_id']} '{asset['asset_name']}' | {asset['endorsement']} | "
                f"model {asset['model_id']} | owner {asset['owner_name']} | score {asset['match_score']}"
            )
    elif agent_name == "KpiIntelligenceAgent":
        print(f"    {output['summary']}")
        for match in output["matches"]:
            print(
                f"    DB evidence: '{match['requested_metric']}' -> {match['matched_kpi_id']} "
                f"'{match['matched_kpi_name']}' ({match['approval_status']}/{match['definition_status']})"
            )
        for review in output["llm_review"]:
            print(f"    LLM advisory: '{review['requested_metric']}' -> {review['matched_kpi_id']}: {review['assessment']}. {review['note']}")
    elif agent_name == "DuplicationAgent":
        print(f"    {output['explanation']}")
    elif agent_name == "GovernanceAgent":
        print(f"    rules evaluated: {output['applicable_rule_ids']}")
        print(f"    request-specific blockers: {len(output['blockers'])}  warnings: {len(output['warnings'])}  human approval required: {output['human_approval_required']}")
        print(f"    findings: {len(output['request_finding_ids'])} on this request, {len(output['out_of_scope_finding_ids'])} outside the requested scope (not blockers)")
        for reference in output["evidence_references"][:5]:
            print(f"    DB evidence: {reference}")
    elif agent_name == "DecisionAgent":
        print(f"    decision: {output['decision']} (confidence {output['confidence']})")


def main() -> int:
    prompt = " ".join(sys.argv[1:]).strip() or DEFAULT_PROMPT
    adapter = OllamaAdapter()

    section("Local LLM preflight")
    print(f"Provider: {adapter.provider_name}\nModel:    {adapter.model_name}\nEndpoint: {adapter.base_url}/api/chat")
    reason = adapter.unavailable_reason()
    if reason:
        print(f"\nFAILED: {reason}\nNo inference was run and nothing was simulated. See docs/LOCAL_LLM_SETUP.md.")
        return 2

    section("Business request")
    print(prompt)

    orchestrator = AgentOrchestrator(
        intent_agent=IntentAgent(adapter),
        kpi_agent=KpiIntelligenceAgent(adapter),
        decision_agent=DecisionAgent(adapter),
    )
    writer = SessionLocal()
    started = time.perf_counter()
    try:
        request_id = orchestrator.process_request(prompt, writer).request_id
    finally:
        writer.close()
    elapsed = time.perf_counter() - started

    reader = SessionLocal()
    try:
        traces = (
            reader.query(AgentExecutionTraces)
            .filter(AgentExecutionTraces.request_id == request_id)
            .order_by(AgentExecutionTraces.step_order)
            .all()
        )
        recommendation = (
            reader.query(AssistantRecommendations).filter(AssistantRecommendations.request_id == request_id).one()
        )

        section(f"Persisted agent traces, read back from the database ({request_id})")
        llm_agents = []
        processors = set()
        total_tokens = 0
        for trace in traces:
            metadata = json.loads(trace.execution_metadata_json)
            output = json.loads(trace.output_json)
            print(f"\n[{trace.step_order}] {trace.agent_name}  {trace.trace_id}  {trace.status}  {trace.duration_ms / 1000:.2f}s")
            print(f"    mode: {metadata['execution_mode']}  provider: {metadata['provider']}  model: {metadata['model']}")
            if metadata["fallback_reason"]:
                print(f"    fallback reason: {metadata['fallback_reason']}")
            for call in metadata["llm_calls"]:
                print(
                    f"    LLM call: {call['status']}  schema {call['schema_name']}  attempts {call['attempts']}  "
                    f"{call['duration_ms'] / 1000:.2f}s  tokens {call['prompt_tokens']}+{call['completion_tokens']}  "
                    f"processor {call['processor']}"
                )
                total_tokens += call["total_tokens"] or 0
                processors.add(call["processor"])
            print_handoff(trace.agent_name, output)
            if metadata["execution_mode"] == "LLM_ASSISTED":
                llm_agents.append(trace.agent_name)

        decision_output = json.loads(traces[-1].output_json)
        section("Final recommendation, from assistant_recommendations")
        print(f"Decision:         {recommendation.decision}")
        print(f"Confidence:       {recommendation.confidence}")
        print(f"Approval needed:  {recommendation.approval_required}")
        print(f"Recommendation:   {recommendation.primary_recommendation}")
        print(f"Rationale:        {recommendation.rationale}")
        print(f"Blockers:         {len(json.loads(recommendation.blockers_json))}")
        print(f"Warnings:         {len(json.loads(recommendation.warnings_json))}")
        print(f"LLM narrative:    {decision_output['llm_narrative'] or '(none: see the DecisionAgent trace)'}")
    finally:
        reader.close()

    section("Inference placement, from Ollama /api/ps")
    with httpx.Client(timeout=5, trust_env=False) as client:
        loaded = client.get(f"{adapter.base_url}/api/ps").json().get("models", [])
    for model in loaded:
        print(f"{model['name']}: size {model['size']} bytes, in GPU memory {model.get('size_vram', 0)} bytes, context {model.get('context_length')}")
    print(f"Models loaded: {len(loaded)}")
    print(f"Detected processor across calls: {sorted(processors)}")

    section("Result")
    print(f"LLM-assisted agents: {llm_agents}")
    print(f"Total tokens: {total_tokens}\nTotal workflow time: {elapsed:.2f}s")
    if len(llm_agents) < REQUIRED_LLM_AGENTS:
        print(f"FAILED: needed {REQUIRED_LLM_AGENTS} LLM-assisted agents, got {len(llm_agents)}.")
        return 1
    print("PASSED: real local inference, with persisted traces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
