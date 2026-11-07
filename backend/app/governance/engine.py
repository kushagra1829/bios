import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.governance.schemas import (
    RuleId,
    FindingSeverity,
    FindingStatus,
    EvaluationRunSummary,
    GovernanceFindingCreate,
)
from backend.app.governance.evidence import compute_finding_id
from backend.app.governance.registry import registry
from backend.app.models.governance import GovernanceEvaluationRuns, GovernanceFindings

logger = logging.getLogger(__name__)


class GovernanceEngine:
    """
    Deterministic governance intelligence engine for BIOS.
    Orchestrates rule evaluations against the relational data store,
    manages finding lifecycles (open, persisting, resolved), and persists
    structured, evidence-backed evaluation runs.
    """

    def __init__(self, rule_registry=registry):
        self.registry = rule_registry

    def evaluate_all(self, db: Session, run_id: Optional[str] = None) -> EvaluationRunSummary:
        """
        Execute full governance evaluation across all eight rules.
        Compares findings with prior active runs to track persistence and resolution.
        Transactional and idempotent.
        """
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)
        run_id = run_id or f"RUN-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Initialize evaluation run record
        eval_run = GovernanceEvaluationRuns(
            run_id=run_id,
            started_at=now_utc,
            status="in_progress",
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
        )
        db.add(eval_run)
        db.flush()

        try:
            # 1. Fetch currently open / persisting findings from database to track lifecycle
            active_existing_findings = (
                db.query(GovernanceFindings)
                .filter(GovernanceFindings.status.in_([FindingStatus.OPEN.value, FindingStatus.PERSISTING.value]))
                .all()
            )
            existing_finding_ids = {f.finding_id: f for f in active_existing_findings}

            # 2. Execute all rules
            all_findings_to_create: List[GovernanceFindingCreate] = []
            for rule in self.registry.get_all():
                logger.info(f"Executing governance rule {rule.rule_id} ({rule.rule_name})")
                rule_findings = rule.evaluate(db)
                all_findings_to_create.extend(rule_findings)

            # 3. Process findings and determine lifecycle state
            current_finding_ids = set()
            persisted_entities = []

            severity_counts = {
                FindingSeverity.CRITICAL.value: 0,
                FindingSeverity.HIGH.value: 0,
                FindingSeverity.MEDIUM.value: 0,
                FindingSeverity.LOW.value: 0,
                FindingSeverity.INFO.value: 0,
            }
            rule_counts: Dict[str, int] = {r.value: 0 for r in RuleId}
            status_counts: Dict[str, int] = {
                FindingStatus.OPEN.value: 0,
                FindingStatus.PERSISTING.value: 0,
                FindingStatus.RESOLVED.value: 0,
            }

            for f_create in all_findings_to_create:
                f_id = compute_finding_id(
                    rule_id=f_create.rule_id.value,
                    entity_type=f_create.target_entity_type.value,
                    entity_id=f_create.target_entity_id,
                    category=f_create.category,
                )
                current_finding_ids.add(f_id)

                # Determine if OPEN or PERSISTING
                if f_id in existing_finding_ids:
                    status = FindingStatus.PERSISTING
                else:
                    status = FindingStatus.OPEN

                evidence_dict = f_create.evidence_bundle.model_dump(mode="json")
                evidence_json_str = json.dumps(evidence_dict)

                # If finding already exists in DB, update with new run and persisting status
                existing_record = db.query(GovernanceFindings).filter(GovernanceFindings.finding_id == f_id).first()
                if existing_record:
                    existing_record.run_id = run_id
                    existing_record.status = status.value
                    existing_record.title = f_create.title
                    existing_record.explanation = f_create.explanation
                    existing_record.observed_value = f_create.observed_value
                    existing_record.expected_condition = f_create.expected_condition
                    existing_record.recommended_action = f_create.recommended_action
                    existing_record.evidence_json = evidence_json_str
                    existing_record.resolved_at = None
                else:
                    new_finding = GovernanceFindings(
                        finding_id=f_id,
                        run_id=run_id,
                        rule_id=f_create.rule_id.value,
                        target_entity_type=f_create.target_entity_type.value,
                        target_entity_id=f_create.target_entity_id,
                        category=f_create.category,
                        severity=f_create.severity.value,
                        status=status.value,
                        title=f_create.title,
                        explanation=f_create.explanation,
                        observed_value=f_create.observed_value,
                        expected_condition=f_create.expected_condition,
                        recommended_action=f_create.recommended_action,
                        human_approval_required=f_create.human_approval_required,
                        evidence_json=evidence_json_str,
                        detected_at=now_utc,
                    )
                    db.add(new_finding)

                # Count metrics
                severity_counts[f_create.severity.value] = severity_counts.get(f_create.severity.value, 0) + 1
                rule_counts[f_create.rule_id.value] = rule_counts.get(f_create.rule_id.value, 0) + 1
                status_counts[status.value] = status_counts.get(status.value, 0) + 1

            # 4. Resolve findings that were previously active but are no longer present
            for old_id, old_finding in existing_finding_ids.items():
                if old_id not in current_finding_ids:
                    old_finding.status = FindingStatus.RESOLVED.value
                    old_finding.resolved_at = now_utc
                    status_counts[FindingStatus.RESOLVED.value] = status_counts.get(FindingStatus.RESOLVED.value, 0) + 1

            # 5. Finalize evaluation run record
            duration_ms = (time.time() - start_time) * 1000.0
            completed_utc = datetime.now(timezone.utc)

            eval_run.status = "success"
            eval_run.completed_at = completed_utc
            eval_run.total_findings = len(all_findings_to_create)
            eval_run.critical_count = severity_counts[FindingSeverity.CRITICAL.value]
            eval_run.high_count = severity_counts[FindingSeverity.HIGH.value]
            eval_run.medium_count = severity_counts[FindingSeverity.MEDIUM.value]
            eval_run.low_count = severity_counts[FindingSeverity.LOW.value]
            eval_run.info_count = severity_counts[FindingSeverity.INFO.value]

            summary_payload = {
                "run_id": run_id,
                "status": "success",
                "started_at": now_utc.isoformat(),
                "completed_at": completed_utc.isoformat(),
                "execution_time_ms": round(duration_ms, 2),
                "total_findings": len(all_findings_to_create),
                "findings_by_severity": severity_counts,
                "findings_by_rule": rule_counts,
                "findings_by_status": status_counts,
            }
            eval_run.summary_json = json.dumps(summary_payload)

            db.commit()

            return EvaluationRunSummary(
                run_id=run_id,
                status="success",
                started_at=now_utc.isoformat(),
                completed_at=completed_utc.isoformat(),
                total_findings=len(all_findings_to_create),
                findings_by_rule=rule_counts,
                findings_by_severity=severity_counts,
                findings_by_status=status_counts,
                execution_time_ms=round(duration_ms, 2),
            )

        except Exception as e:
            db.rollback()
            logger.error(f"Governance evaluation run {run_id} failed: {e}", exc_info=True)
            # Record failed run
            failed_run = db.query(GovernanceEvaluationRuns).filter(GovernanceEvaluationRuns.run_id == run_id).first()
            if failed_run:
                failed_run.status = "failed"
                failed_run.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise

    def evaluate_rule(self, rule_id: RuleId, db: Session) -> List[GovernanceFindingCreate]:
        """Execute a single governance rule independently without changing global run state."""
        rule = self.registry.get(rule_id)
        if not rule:
            raise ValueError(f"Rule {rule_id} is not registered.")
        return rule.evaluate(db)

    def get_summary(self, db: Session) -> Dict[str, Any]:
        """Aggregate finding metrics, severity distribution, and latest evaluation metadata."""
        latest_run = (
            db.query(GovernanceEvaluationRuns)
            .filter(GovernanceEvaluationRuns.status == "success")
            .order_by(GovernanceEvaluationRuns.completed_at.desc())
            .first()
        )

        # Active findings aggregation
        active_findings = (
            db.query(GovernanceFindings)
            .filter(GovernanceFindings.status.in_([FindingStatus.OPEN.value, FindingStatus.PERSISTING.value]))
            .all()
        )

        by_severity: Dict[str, int] = {}
        by_rule: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_entity: Dict[str, int] = {}

        for f in active_findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
            by_status[f.status] = by_status.get(f.status, 0) + 1
            by_entity[f.target_entity_type] = by_entity.get(f.target_entity_type, 0) + 1

        resolved_count = (
            db.query(GovernanceFindings)
            .filter(GovernanceFindings.status == FindingStatus.RESOLVED.value)
            .count()
        )

        return {
            "total_active_findings": len(active_findings),
            "total_resolved_findings": resolved_count,
            "findings_by_severity": by_severity,
            "findings_by_rule": by_rule,
            "findings_by_status": by_status,
            "findings_by_entity_type": by_entity,
            "latest_run": (
                {
                    "run_id": latest_run.run_id,
                    "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
                    "total_findings": latest_run.total_findings,
                }
                if latest_run
                else None
            ),
        }


# Global engine singleton
engine = GovernanceEngine()

