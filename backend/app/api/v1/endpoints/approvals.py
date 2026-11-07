from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.approvals.service import approval_service
from backend.app.approvals.schemas import (
    ApprovalCreate,
    ApprovalOut,
    ApprovalDecisionPayload,
    ApprovalTransitionOut,
    ApprovalQueueSummaryOut,
)
from backend.app.models.approval import ApprovalRequests, ApprovalStateTransitions

router = APIRouter()


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def submit_approval_request(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a human approval request for consequential lifecycle changes,
    migration actions, semantic model adjustments, or governance exceptions.
    """
    try:
        approval = approval_service.create_request(payload, db)
        return approval
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to submit approval request: {str(e)}",
        )


@router.get("", response_model=List[ApprovalOut])
def list_approvals(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (PENDING, APPROVED, REJECTED, etc.)"),
    required_role: Optional[str] = Query(None, description="Filter by required reviewer role"),
    target_entity_type: Optional[str] = Query(None, description="Filter by entity type (asset, model, kpi, etc.)"),
    requester_id: Optional[str] = Query(None, description="Filter by requester ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List approval requests with pagination and status/role filters."""
    query = db.query(ApprovalRequests)

    if status_filter:
        query = query.filter(ApprovalRequests.status == status_filter.upper())
    if required_role:
        query = query.filter(ApprovalRequests.required_role == required_role.upper())
    if target_entity_type:
        query = query.filter(ApprovalRequests.target_entity_type == target_entity_type.lower())
    if requester_id:
        query = query.filter(ApprovalRequests.requester_id == requester_id)

    approvals = (
        query.order_by(desc(ApprovalRequests.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return approvals


@router.get("/summary", response_model=ApprovalQueueSummaryOut)
def get_approval_queue_summary(
    db: Session = Depends(get_db),
):
    """Retrieve aggregate queue metrics across pending, approved, and rejected approvals."""
    return approval_service.get_queue_summary(db)


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(
    approval_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve details for a single approval request."""
    approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found.",
        )
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve_request(
    approval_id: str,
    payload: ApprovalDecisionPayload,
    db: Session = Depends(get_db),
):
    """
    Authorize and approve an active approval request.
    Enforces RBAC authority, anti-self-approval restrictions, and governance blocker safeguards.
    """
    try:
        return approval_service.approve_request(approval_id, payload, db)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject_request(
    approval_id: str,
    payload: ApprovalDecisionPayload,
    db: Session = Depends(get_db),
):
    """
    Reject an approval request with a mandatory substantive reason.
    """
    try:
        return approval_service.reject_request(approval_id, payload, db)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{approval_id}/request-changes", response_model=ApprovalOut)
def request_changes(
    approval_id: str,
    payload: ApprovalDecisionPayload,
    db: Session = Depends(get_db),
):
    """
    Request modifications on an approval request with reviewer comments.
    """
    try:
        return approval_service.request_changes(approval_id, payload, db)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{approval_id}/history", response_model=List[ApprovalTransitionOut])
def get_approval_history(
    approval_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the full state transition history for an approval request.
    """
    approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found.",
        )

    transitions = (
        db.query(ApprovalStateTransitions)
        .filter(ApprovalStateTransitions.approval_id == approval_id)
        .order_by(ApprovalStateTransitions.transitioned_at.asc())
        .all()
    )
    return transitions

