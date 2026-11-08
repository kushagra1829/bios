import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from backend.app.models.monitoring import MonitoringExecutionRuns, GovernanceAlerts
from backend.app.models.governance import GovernanceFindings, GovernanceEvaluationRuns
from backend.app.models.core import AnalyticsAssets, SemanticModels, Owners, LineageEdges
from backend.app.governance.engine import GovernanceEngine
from backend.app.integrations.registry import integration_registry

logger = logging.getLogger("bios.monitoring.engine")


class ContinuousGovernanceEngine:
    """
    Continuous governance monitoring and alert generation service.
    Re-evaluates deterministic governance rules, synchronizes external BI catalogues,
    identifies newly introduced defects, and manages the lifecycle of governance alerts.
    """

    def __init__(self, governance_engine: Optional[GovernanceEngine] = None):
        self.governance_engine = governance_engine or GovernanceEngine()

    def run_monitoring_job(
        self,
        db: Session,
        job_type: str = "FULL_CONTINUOUS_SCAN",
        triggered_by: str = "SYSTEM_SCHEDULER",
    ) -> MonitoringExecutionRuns:
        """
        Execute a scheduled or on-demand monitoring job with concurrency protection.
        """
        now_utc = datetime.now(timezone.utc)
        job_id = f"JOB-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # 1. Concurrency guard: check if the same job type is currently running
        active_job = (
            db.query(MonitoringExecutionRuns)
            .filter(
                MonitoringExecutionRuns.job_type == job_type,
                MonitoringExecutionRuns.status == "RUNNING",
            )
            .first()
        )
        if active_job:
            logger.warning("Monitoring job '%s' already running (%s). Skipping concurrent run.", job_type, active_job.job_id)
            skip_run = MonitoringExecutionRuns(
                job_id=job_id,
                job_type=job_type,
                status="FAILED",
                started_at=now_utc,
                completed_at=now_utc,
                duration_ms=0,
                errors=f"Concurrent execution blocked: Active job {active_job.job_id} is currently running.",
                source_connector="INTERNAL",
            )
            db.add(skip_run)
            db.commit()
            return skip_run

        # 2. Initialize job run record
        job_run = MonitoringExecutionRuns(
            job_id=job_id,
            job_type=job_type,
            status="RUNNING",
            started_at=now_utc,
            records_processed=0,
            findings_generated=0,
            findings_resolved=0,
            source_connector="INTERNAL",
        )
        db.add(job_run)
        db.commit()

        start_time = time.time()
        errors_list: List[str] = []
        details: Dict[str, Any] = {"triggered_by": triggered_by}

        try:
            if job_type in ("CATALOG_SYNC", "FULL_CONTINUOUS_SCAN"):
                self._execute_catalog_sync(db, job_run, details, errors_list)

            if job_type in ("GOVERNANCE_REEVAL", "FULL_CONTINUOUS_SCAN"):
                self._execute_governance_reeval(db, job_run, details, errors_list)

            if job_type in ("DUPLICATE_DETECTION", "FULL_CONTINUOUS_SCAN"):
                self._execute_duplicate_audit(db, job_run, details, errors_list)

            if job_type in ("OWNERSHIP_AUDIT", "FULL_CONTINUOUS_SCAN"):
                self._execute_ownership_audit(db, job_run, details, errors_list)

            if job_type in ("SEMANTIC_READINESS", "FULL_CONTINUOUS_SCAN"):
                self._execute_semantic_readiness_audit(db, job_run, details, errors_list)

            # 3. Synchronize Findings to Governance Alerts
            self._sync_findings_to_alerts(db, job_run, details)

            job_run.status = "SUCCESS" if not errors_list else "PARTIAL_SUCCESS"
            if errors_list:
                job_run.errors = "\n".join(errors_list)

        except Exception as e:
            db.rollback()
            logger.error("Continuous monitoring job failed (%s): %s", job_id, e, exc_info=True)
            job_run.status = "FAILED"
            job_run.errors = str(e)
            errors_list.append(str(e))

        finally:
            end_time = time.time()
            job_run.completed_at = datetime.now(timezone.utc)
            job_run.duration_ms = int((end_time - start_time) * 1000)
            job_run.details_json = json.dumps(details)
            db.commit()

        return job_run

    def _execute_catalog_sync(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Trigger catalogue synchronization across all registered BI connectors."""
        sync_results = integration_registry.synchronize_all(db=db)
        sync_summary = {}
        total_imported = 0

        for c_id, res in sync_results.items():
            sync_summary[c_id] = {
                "status": res.status,
                "workspaces": res.imported_workspaces,
                "reports": res.imported_reports,
                "models": res.imported_models,
                "updated": res.updated_assets,
                "errors": res.errors,
            }
            total_imported += res.imported_reports
            if res.errors:
                errors.extend([f"[{c_id}] {err}" for err in res.errors])

        details["catalog_sync"] = sync_summary
        job_run.records_processed += total_imported

    def _execute_governance_reeval(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Re-evaluate the 8 deterministic rules across all entities."""
        summary = self.governance_engine.evaluate_all(db=db)
        details["governance_evaluation"] = {
            "run_id": summary.run_id,
            "total_findings": summary.total_findings,
            "critical": summary.findings_by_severity.get("critical", 0),
            "high": summary.findings_by_severity.get("high", 0),
            "medium": summary.findings_by_severity.get("medium", 0),
            "low": summary.findings_by_severity.get("low", 0),
            "resolved": summary.findings_by_status.get("resolved", 0),
        }
        job_run.findings_generated += summary.total_findings
        job_run.findings_resolved += summary.findings_by_status.get("resolved", 0)
        job_run.records_processed += summary.total_findings

    def _execute_duplicate_audit(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Audit for duplicate dashboard names or cross-platform overlaps."""
        duplicate_clusters = (
            db.query(AnalyticsAssets.asset_name, func.count(AnalyticsAssets.asset_id))
            .group_by(AnalyticsAssets.asset_name)
            .having(func.count(AnalyticsAssets.asset_id) > 1)
            .all()
        )
        details["duplicate_clusters_found"] = len(duplicate_clusters)

    def _execute_ownership_audit(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Audit unowned assets and assets with inactive owners."""
        unowned_count = db.query(AnalyticsAssets).filter(AnalyticsAssets.owner_id.is_(None)).count()
        inactive_owner_count = (
            db.query(AnalyticsAssets)
            .join(Owners, AnalyticsAssets.owner_id == Owners.owner_id)
            .filter(Owners.status == "inactive")
            .count()
        )
        details["unowned_assets_count"] = unowned_count
        details["inactive_owner_assets_count"] = inactive_owner_count

    def _execute_semantic_readiness_audit(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Audit semantic model health and AI readiness."""
        poor_models = db.query(SemanticModels).filter(SemanticModels.ai_readiness == "poor").count()
        warning_models = db.query(SemanticModels).filter(SemanticModels.refresh_status == "warning").count()
        failed_models = db.query(SemanticModels).filter(SemanticModels.refresh_status == "failed").count()

        details["semantic_model_readiness"] = {
            "poor_readiness_count": poor_models,
            "warning_refresh_count": warning_models,
            "failed_refresh_count": failed_models,
        }

    def _sync_findings_to_alerts(
        self,
        db: Session,
        job_run: MonitoringExecutionRuns,
        details: Dict[str, Any],
    ) -> None:
        """
        Synchronize active Critical and High findings into the GovernanceAlerts queue.
        Resolves alerts if underlying findings have been resolved.
        Preserves ACKNOWLEDGED status without resolving the underlying governance violation.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Fetch all currently open or persisting critical/high findings
        actionable_findings = (
            db.query(GovernanceFindings)
            .filter(
                GovernanceFindings.status.in_(["open", "persisting"]),
                GovernanceFindings.severity.in_(["critical", "high"]),
            )
            .all()
        )

        active_finding_ids = set()
        alerts_created = 0
        alerts_updated = 0

        for f in actionable_findings:
            active_finding_ids.add(f.finding_id)
            alert = db.query(GovernanceAlerts).filter(GovernanceAlerts.finding_id == f.finding_id).first()

            if not alert:
                alert_id = f"ALT-{f.finding_id}"
                new_alert = GovernanceAlerts(
                    alert_id=alert_id,
                    finding_id=f.finding_id,
                    rule_id=f.rule_id,
                    target_entity_type=f.target_entity_type,
                    target_entity_id=f.target_entity_id,
                    severity=f.severity,
                    status="NEW",
                    title=f.title,
                    explanation=f.explanation,
                    recommended_action=f.recommended_action,
                    created_at=now_utc,
                )
                db.add(new_alert)
                alerts_created += 1
            else:
                # Existing alert: update title or explanation if modified, keep status if acknowledged
                if alert.status == "RESOLVED":
                    alert.status = "NEW"  # Re-opened defect
                    alert.resolved_at = None
                alerts_updated += 1

        # 2. Resolve alerts whose underlying findings are now resolved
        resolved_findings = (
            db.query(GovernanceFindings)
            .filter(GovernanceFindings.status == "resolved")
            .all()
        )
        resolved_finding_ids = {rf.finding_id for rf in resolved_findings}

        open_alerts = (
            db.query(GovernanceAlerts)
            .filter(GovernanceAlerts.status.in_(["NEW", "ACKNOWLEDGED"]))
            .all()
        )

        resolved_alerts_count = 0
        for oa in open_alerts:
            if oa.finding_id in resolved_finding_ids:
                oa.status = "RESOLVED"
                oa.resolved_at = now_utc
                resolved_alerts_count += 1

        db.flush()
        details["alerts_synchronization"] = {
            "alerts_created": alerts_created,
            "alerts_updated": alerts_updated,
            "alerts_resolved": resolved_alerts_count,
        }

    def get_monitoring_summary(self, db: Session) -> Dict[str, Any]:
        """Provide telemetry and recent history for the monitoring dashboard."""
        total_jobs = db.query(MonitoringExecutionRuns).count()
        successful_jobs = db.query(MonitoringExecutionRuns).filter(MonitoringExecutionRuns.status == "SUCCESS").count()
        failed_jobs = db.query(MonitoringExecutionRuns).filter(MonitoringExecutionRuns.status == "FAILED").count()

        latest_run = (
            db.query(MonitoringExecutionRuns)
            .order_by(MonitoringExecutionRuns.started_at.desc())
            .first()
        )

        # Alerts summary
        critical_alerts = db.query(GovernanceAlerts).filter(GovernanceAlerts.status != "RESOLVED", GovernanceAlerts.severity == "critical").count()
        high_alerts = db.query(GovernanceAlerts).filter(GovernanceAlerts.status != "RESOLVED", GovernanceAlerts.severity == "high").count()
        acknowledged_alerts = db.query(GovernanceAlerts).filter(GovernanceAlerts.status == "ACKNOWLEDGED").count()
        resolved_alerts = db.query(GovernanceAlerts).filter(GovernanceAlerts.status == "RESOLVED").count()

        return {
            "monitoring_active": True,
            "total_jobs_executed": total_jobs,
            "successful_jobs": successful_jobs,
            "failed_jobs": failed_jobs,
            "latest_run": {
                "job_id": latest_run.job_id if latest_run else None,
                "job_type": latest_run.job_type if latest_run else None,
                "status": latest_run.status if latest_run else None,
                "started_at": latest_run.started_at.isoformat() if latest_run and latest_run.started_at else None,
                "duration_ms": latest_run.duration_ms if latest_run else 0,
            } if latest_run else None,
            "alerts": {
                "unresolved_critical": critical_alerts,
                "unresolved_high": high_alerts,
                "acknowledged": acknowledged_alerts,
                "resolved": resolved_alerts,
            },
        }


# Global singleton instance
continuous_monitoring_engine = ContinuousGovernanceEngine()
