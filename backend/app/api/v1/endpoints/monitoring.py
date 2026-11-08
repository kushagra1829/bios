from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.monitoring.engine import continuous_monitoring_engine
from backend.app.models.monitoring import MonitoringExecutionRuns
from backend.app.auth.dependencies import require_role
from backend.app.auth.schemas import UserRole, UserContext

router = APIRouter()


class JobTriggerRequest(BaseModel):
    job_type: str = "FULL_CONTINUOUS_SCAN"
    actor: str = "ADMIN_MANUAL"


class MonitoringJobOut(BaseModel):
    job_id: str
    job_type: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: int
    records_processed: int
    findings_generated: int
    findings_resolved: int
    errors: Optional[str] = None
    source_connector: Optional[str] = None
    details_json: Optional[str] = None


@router.get("/summary")
def get_monitoring_summary(
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """Summary telemetry of continuous governance monitoring runs, alerts, and engine status."""
    return continuous_monitoring_engine.get_monitoring_summary(db=db)


@router.get("/jobs", response_model=List[MonitoringJobOut])
def list_monitoring_jobs(
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, RUNNING, FAILED)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """List historical continuous governance monitoring executions."""
    query = db.query(MonitoringExecutionRuns)
    if job_type:
        query = query.filter(MonitoringExecutionRuns.job_type == job_type)
    if status:
        query = query.filter(MonitoringExecutionRuns.status == status)

    jobs = query.order_by(desc(MonitoringExecutionRuns.started_at)).offset(offset).limit(limit).all()

    return [
        MonitoringJobOut(
            job_id=j.job_id,
            job_type=j.job_type,
            status=j.status,
            started_at=j.started_at.isoformat() if j.started_at else "",
            completed_at=j.completed_at.isoformat() if j.completed_at else None,
            duration_ms=j.duration_ms,
            records_processed=j.records_processed,
            findings_generated=j.findings_generated,
            findings_resolved=j.findings_resolved,
            errors=j.errors,
            source_connector=j.source_connector,
            details_json=j.details_json,
        )
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=MonitoringJobOut)
def get_monitoring_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """Fetch details for a specific continuous monitoring execution."""
    j = db.query(MonitoringExecutionRuns).filter(MonitoringExecutionRuns.job_id == job_id).first()
    if not j:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring job '{job_id}' not found.",
        )
    return MonitoringJobOut(
        job_id=j.job_id,
        job_type=j.job_type,
        status=j.status,
        started_at=j.started_at.isoformat() if j.started_at else "",
        completed_at=j.completed_at.isoformat() if j.completed_at else None,
        duration_ms=j.duration_ms,
        records_processed=j.records_processed,
        findings_generated=j.findings_generated,
        findings_resolved=j.findings_resolved,
        errors=j.errors,
        source_connector=j.source_connector,
        details_json=j.details_json,
    )


@router.post("/jobs/run", response_model=MonitoringJobOut)
def run_monitoring_job(
    payload: JobTriggerRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """Trigger an on-demand governance monitoring execution."""
    job = continuous_monitoring_engine.run_monitoring_job(
        db=db,
        job_type=payload.job_type,
        triggered_by=payload.actor,
    )
    return MonitoringJobOut(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at.isoformat() if job.started_at else "",
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_ms=job.duration_ms,
        records_processed=job.records_processed,
        findings_generated=job.findings_generated,
        findings_resolved=job.findings_resolved,
        errors=job.errors,
        source_connector=job.source_connector,
        details_json=job.details_json,
    )

