from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.models.monitoring import GovernanceAlerts
from backend.app.models.governance import GovernanceFindings
from backend.app.auth.dependencies import require_role, get_current_user
from backend.app.auth.schemas import UserRole, UserContext

router = APIRouter(
    dependencies=[Depends(require_role(UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN))]
)


class AlertAcknowledgeRequest(BaseModel):
    actor_id: str
    actor_role: str
    rationale: str = Field(..., min_length=5, description="Documented reason for acknowledging alert without resolving violation.")


class GovernanceAlertOut(BaseModel):
    alert_id: str
    finding_id: str
    rule_id: str
    target_entity_type: str
    target_entity_id: str
    severity: str
    status: str
    title: str
    explanation: str
    recommended_action: str
    created_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledgement_rationale: Optional[str] = None
    resolved_at: Optional[str] = None


class AlertsSummaryOut(BaseModel):
    total_active_alerts: int
    by_severity: dict
    by_status: dict


@router.get("", response_model=List[GovernanceAlertOut])
def list_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (NEW, ACKNOWLEDGED, RESOLVED)"),
    rule_id: Optional[str] = Query(None, description="Filter by rule ID"),
    search: Optional[str] = Query(None, description="Search term in title or target entity ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List governance alerts with multi-dimensional filtering."""
    query = db.query(GovernanceAlerts)

    if severity:
        query = query.filter(GovernanceAlerts.severity == severity.lower())
    if status_filter:
        query = query.filter(GovernanceAlerts.status == status_filter.upper())
    if rule_id:
        query = query.filter(GovernanceAlerts.rule_id == rule_id)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (GovernanceAlerts.title.ilike(search_pattern))
            | (GovernanceAlerts.target_entity_id.ilike(search_pattern))
        )

    alerts = query.order_by(desc(GovernanceAlerts.created_at)).offset(offset).limit(limit).all()

    return [
        GovernanceAlertOut(
            alert_id=a.alert_id,
            finding_id=a.finding_id,
            rule_id=a.rule_id,
            target_entity_type=a.target_entity_type,
            target_entity_id=a.target_entity_id,
            severity=a.severity,
            status=a.status,
            title=a.title,
            explanation=a.explanation,
            recommended_action=a.recommended_action,
            created_at=a.created_at.isoformat() if a.created_at else "",
            acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            acknowledged_by=a.acknowledged_by,
            acknowledgement_rationale=a.acknowledgement_rationale,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        )
        for a in alerts
    ]


@router.get("/summary", response_model=AlertsSummaryOut)
def get_alerts_summary(db: Session = Depends(get_db)):
    """Summary counts of governance alerts by severity and status."""
    all_alerts = db.query(GovernanceAlerts).all()

    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_status = {"NEW": 0, "ACKNOWLEDGED": 0, "RESOLVED": 0}
    total_active = 0

    for a in all_alerts:
        sev = a.severity.lower()
        if sev in by_severity:
            by_severity[sev] += 1
        st = a.status.upper()
        if st in by_status:
            by_status[st] += 1
        if st in ("NEW", "ACKNOWLEDGED"):
            total_active += 1

    return AlertsSummaryOut(
        total_active_alerts=total_active,
        by_severity=by_severity,
        by_status=by_status,
    )


@router.get("/{alert_id}", response_model=GovernanceAlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    """Fetch details for a specific governance alert."""
    a = db.query(GovernanceAlerts).filter(GovernanceAlerts.alert_id == alert_id).first()
    if not a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Governance alert '{alert_id}' not found.",
        )
    return GovernanceAlertOut(
        alert_id=a.alert_id,
        finding_id=a.finding_id,
        rule_id=a.rule_id,
        target_entity_type=a.target_entity_type,
        target_entity_id=a.target_entity_id,
        severity=a.severity,
        status=a.status,
        title=a.title,
        explanation=a.explanation,
        recommended_action=a.recommended_action,
        created_at=a.created_at.isoformat() if a.created_at else "",
        acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        acknowledged_by=a.acknowledged_by,
        acknowledgement_rationale=a.acknowledgement_rationale,
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
    )


@router.post("/{alert_id}/acknowledge", response_model=GovernanceAlertOut)
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
):
    """
    Acknowledge a governance alert with mandatory justification.
    NOTE: Acknowledging an alert does NOT resolve the underlying governance finding.
    The finding remains active in the governance engine until remediation is completed.
    """
    a = db.query(GovernanceAlerts).filter(GovernanceAlerts.alert_id == alert_id).first()
    if not a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Governance alert '{alert_id}' not found.",
        )

    if a.status == "RESOLVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot acknowledge an alert that has already been resolved by remediation.",
        )

    now_utc = datetime.now(timezone.utc)
    a.status = "ACKNOWLEDGED"
    a.acknowledged_at = now_utc
    a.acknowledged_by = f"{payload.actor_id} ({payload.actor_role})"
    a.acknowledgement_rationale = payload.rationale.strip()

    db.commit()
    db.refresh(a)

    return GovernanceAlertOut(
        alert_id=a.alert_id,
        finding_id=a.finding_id,
        rule_id=a.rule_id,
        target_entity_type=a.target_entity_type,
        target_entity_id=a.target_entity_id,
        severity=a.severity,
        status=a.status,
        title=a.title,
        explanation=a.explanation,
        recommended_action=a.recommended_action,
        created_at=a.created_at.isoformat() if a.created_at else "",
        acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        acknowledged_by=a.acknowledged_by,
        acknowledgement_rationale=a.acknowledgement_rationale,
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
    )

