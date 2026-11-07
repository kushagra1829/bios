from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.approvals.schemas import AuditEventOut
from backend.app.models.approval import AuditEvents

router = APIRouter()


@router.get("/events", response_model=List[AuditEventOut])
def list_audit_events(
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    actor_role: Optional[str] = Query(None, description="Filter by actor role"),
    event_type: Optional[str] = Query(None, description="Filter by event type (APPROVAL_REQUESTED, APPROVAL_GRANTED, etc.)"),
    target_entity_type: Optional[str] = Query(None, description="Filter by entity type (asset, model, kpi, etc.)"),
    target_entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Retrieve the immutable append-only audit trail of consequential human approvals,
    lifecycle decisions, and governance actions.
    """
    query = db.query(AuditEvents)

    if actor_id:
        query = query.filter(AuditEvents.actor_id == actor_id)
    if actor_role:
        query = query.filter(AuditEvents.actor_role == actor_role.upper())
    if event_type:
        query = query.filter(AuditEvents.event_type == event_type.upper())
    if target_entity_type:
        query = query.filter(AuditEvents.target_entity_type == target_entity_type.lower())
    if target_entity_id:
        query = query.filter(AuditEvents.target_entity_id == target_entity_id)

    events = (
        query.order_by(desc(AuditEvents.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return events

