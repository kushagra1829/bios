import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from backend.app.agents.answering.final_validation import validate_final_decision
from backend.app.agents.answering.presentation import build_presentation
from backend.app.agents.execution import capture_execution
from backend.app.agents.schemas import (
    BusinessIntent,
    DiscoveryResult,
    KpiAnalysisResult,
    DuplicationResult,
    GovernanceAgentResult,
    DecisionResult,
    AssistantWorkflowResponse,
    AgentTraceOut,
)
from backend.app.agents.specialists.intent_agent import IntentAgent
from backend.app.agents.specialists.discovery_agent import DiscoveryAgent
from backend.app.agents.specialists.kpi_agent import KpiIntelligenceAgent
from backend.app.agents.specialists.duplication_agent import DuplicationAgent
from backend.app.agents.specialists.governance_agent import GovernanceAgent
from backend.app.agents.specialists.decision_agent import DecisionAgent
from backend.app.models.assistant import (
    AssistantRequests,
    AgentExecutionTraces,
    AssistantRecommendations,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Central Multi-Agent Orchestrator for BIOS Analytics Assistant.
    Coordinates the collaborative specialist agents across a shared business request:
      Step 1: IntentAgent -> parses natural-language prompt into structured intent.
      Step 2: DiscoveryAgent -> searches catalog for existing assets across match tiers.
      Step 3: KpiIntelligenceAgent -> reconciles requested metrics against canonical KPI catalog.
      Step 4: DuplicationAgent -> multi-factor structural/KPI/semantic duplication analysis.
      Step 5: GovernanceAgent -> checks ownership, lineage, endorsement, active findings.
      Step 6: DecisionAgent -> synthesizes findings into authoritative recommendation (REUSE/MODIFY/etc).
    Agents run strictly one at a time. Traces record timing, inputs, outputs, and the
    provider, model and execution mode that actually produced each step.
    """

    def __init__(
        self,
        intent_agent: Optional[IntentAgent] = None,
        discovery_agent: Optional[DiscoveryAgent] = None,
        kpi_agent: Optional[KpiIntelligenceAgent] = None,
        duplication_agent: Optional[DuplicationAgent] = None,
        governance_agent: Optional[GovernanceAgent] = None,
        decision_agent: Optional[DecisionAgent] = None,
        max_retries: int = 1,
    ):
        self.intent_agent = intent_agent or IntentAgent()
        self.discovery_agent = discovery_agent or DiscoveryAgent()
        self.kpi_agent = kpi_agent or KpiIntelligenceAgent()
        self.duplication_agent = duplication_agent or DuplicationAgent()
        self.governance_agent = governance_agent or GovernanceAgent()
        self.decision_agent = decision_agent or DecisionAgent()
        self.max_retries = max_retries

    def process_request(
        self,
        prompt: str,
        db: Session,
        request_id: Optional[str] = None,
    ) -> AssistantWorkflowResponse:
        """
        Execute end-to-end multi-agent orchestration for a business request.
        Commits the request and each trace as it completes: failed runs keep their traces,
        and no database write lock is held across slow local inference.
        """
        now_utc = datetime.now(timezone.utc)
        request_id = request_id or f"REQ-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        logger.info(f"[AgentOrchestrator] Starting workflow for request {request_id}: '{prompt[:60]}...'")

        # 1. Create initial AssistantRequest record
        request_record = AssistantRequests(
            request_id=request_id,
            raw_prompt=prompt,
            status="processing",
            created_at=now_utc,
            updated_at=now_utc,
        )
        db.add(request_record)
        db.commit()

        trace_records: List[AgentExecutionTraces] = []
        step_counter = 1

        try:
            # Step 1: Intent Extraction
            intent, trace1 = self._run_step(
                agent_name="IntentAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data={"prompt": prompt},
                func=lambda: self.intent_agent.process(prompt, db),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace1)
            request_record.parsed_intent_json = json.dumps(intent.model_dump(mode="json"))
            db.commit()

            # Step 2: Discovery Search
            discovery, trace2 = self._run_step(
                agent_name="DiscoveryAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data=intent.model_dump(mode="json"),
                func=lambda: self.discovery_agent.process(intent, db),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace2)

            # Step 3: KPI Intelligence
            kpi_analysis, trace3 = self._run_step(
                agent_name="KpiIntelligenceAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data={"requested_kpis": intent.kpis},
                func=lambda: self.kpi_agent.process(intent, db),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace3)

            # Step 4: Duplication Analysis
            duplication, trace4 = self._run_step(
                agent_name="DuplicationAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data={
                    "products": intent.products,
                    "exact_matches": len(discovery.exact_matches),
                    "canonical_kpis": kpi_analysis.canonical_approved_kpi_ids,
                },
                func=lambda: self.duplication_agent.process(intent, discovery, kpi_analysis, db),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace4)

            # Step 5: Governance Guardrails
            governance, trace5 = self._run_step(
                agent_name="GovernanceAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data={
                    "exact_candidates": [a.asset_id for a in discovery.exact_matches],
                    "unapproved_kpis": kpi_analysis.unapproved_or_conflicted_kpi_ids,
                },
                func=lambda: self.governance_agent.process(intent, discovery, kpi_analysis, duplication, db),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace5)

            # Step 6: Decision Synthesis
            recommendation, trace6 = self._run_step(
                agent_name="DecisionAgent",
                step_order=step_counter,
                request_id=request_id,
                input_data={
                    "intent_confidence": intent.confidence,
                    "exact_matches_count": len(discovery.exact_matches),
                    "has_duplicates": duplication.has_duplicates,
                    "governance_blockers_count": len(governance.blockers),
                },
                # The decision (including any LLM narrative) is always passed through deterministic
                # validation before it is traced, persisted or returned. No provider can bypass it.
                func=lambda: validate_final_decision(
                    self.decision_agent.process(intent, discovery, kpi_analysis, duplication, governance, db), db
                ),
                db=db,
            )
            step_counter += 1
            trace_records.append(trace6)

            # 2. Persist Final Recommendation
            rec_id = f"REC-{uuid.uuid4().hex[:8].upper()}"
            rec_record = AssistantRecommendations(
                recommendation_id=rec_id,
                request_id=request_id,
                decision=recommendation.decision.value,
                confidence=recommendation.confidence,
                primary_recommendation=recommendation.primary_recommendation,
                rationale=recommendation.rationale,
                alternatives_json=json.dumps([a.model_dump(mode="json") for a in recommendation.alternatives]),
                blockers_json=json.dumps(recommendation.blockers),
                warnings_json=json.dumps(recommendation.warnings),
                matched_assets_json=json.dumps([a.model_dump(mode="json") for a in discovery.exact_matches[:5]]),
                kpi_analysis_json=json.dumps(kpi_analysis.model_dump(mode="json")),
                duplicate_analysis_json=json.dumps(duplication.model_dump(mode="json")),
                approval_required=recommendation.human_approval_required,
                created_at=datetime.now(timezone.utc),
            )
            db.add(rec_record)

            request_record.status = "completed"
            request_record.updated_at = datetime.now(timezone.utc)
            db.commit()

            # Format trace outputs
            trace_outs = [
                AgentTraceOut(
                    trace_id=t.trace_id,
                    request_id=t.request_id,
                    agent_name=t.agent_name,
                    step_order=t.step_order,
                    status=t.status,
                    duration_ms=t.duration_ms,
                    input_json=t.input_json,
                    output_json=t.output_json,
                    error_message=t.error_message,
                    execution_metadata_json=t.execution_metadata_json,
                    executed_at=t.executed_at,
                )
                for t in trace_records
            ]

            presentation = build_presentation(
                intent, discovery, kpi_analysis, duplication, governance, recommendation,
                discovery.data_answer, discovery.governance_answer, discovery.migration_answer, db,
            )
            return AssistantWorkflowResponse(
                request_id=request_id,
                raw_prompt=prompt,
                status="completed",
                intent=intent,
                recommendation=recommendation,
                discovery=discovery,
                kpi_analysis=kpi_analysis,
                duplication=duplication,
                governance=governance,
                traces=trace_outs,
                request_types=list(intent.request_types),
                data_answer=discovery.data_answer,
                governance_answer=discovery.governance_answer,
                migration_answer=discovery.migration_answer,
                presentation=presentation,
            )

        except Exception as e:
            db.rollback()
            logger.error(f"[AgentOrchestrator] Orchestration failed for {request_id}: {e}", exc_info=True)
            # Update failed status in a separate transaction
            try:
                failed_req = db.query(AssistantRequests).filter(AssistantRequests.request_id == request_id).first()
                if failed_req:
                    failed_req.status = "failed"
                    db.commit()
            except Exception:
                db.rollback()
            raise

    def _run_step(
        self,
        agent_name: str,
        step_order: int,
        request_id: str,
        input_data: Dict[str, Any],
        func: Any,
        db: Session,
    ) -> tuple[Any, AgentExecutionTraces]:
        """Execute a single agent step with timing, retry support, and trace recording."""
        start = time.time()
        trace_id = f"TRC-{uuid.uuid4().hex[:12].upper()}"
        attempts = 0
        last_error: Optional[str] = None
        result = None
        status = "success"

        with capture_execution() as execution:
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    result = func()
                    status = "success"
                    break
                except Exception as ex:
                    last_error = str(ex)
                    logger.warning(f"[{agent_name}] Attempt {attempts} failed: {ex}")
                    if attempts > self.max_retries:
                        status = "failed"
                        duration = (time.time() - start) * 1000.0
                        trace = AgentExecutionTraces(
                            trace_id=trace_id,
                            request_id=request_id,
                            agent_name=agent_name,
                            step_order=step_order,
                            status=status,
                            duration_ms=round(duration, 2),
                            input_json=json.dumps(input_data),
                            output_json=None,
                            error_message=last_error,
                            execution_metadata_json=execution.model_dump_json(),
                            executed_at=datetime.now(timezone.utc),
                        )
                        db.add(trace)
                        db.commit()
                        raise

        duration = (time.time() - start) * 1000.0
        output_payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else str(result)

        trace = AgentExecutionTraces(
            trace_id=trace_id,
            request_id=request_id,
            agent_name=agent_name,
            step_order=step_order,
            status=status,
            duration_ms=round(duration, 2),
            input_json=json.dumps(input_data),
            output_json=json.dumps(output_payload),
            error_message=None,
            execution_metadata_json=execution.model_dump_json(),
            executed_at=datetime.now(timezone.utc),
        )
        db.add(trace)
        db.commit()
        return result, trace


# Global orchestrator singleton
orchestrator = AgentOrchestrator()

