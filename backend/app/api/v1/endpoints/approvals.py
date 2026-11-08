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
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.schemas import UserRole, UserContext

router = APIRouter()


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def submit_approval_request(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """
    Submit a human approval request for consequential lifecycle changes,
    migration actions, semantic model adjustments, or governance exceptions.
    Enforces authentic requester identity from request authorization context.
    """
    # Overwrite requester identity from authenticated user context (never trust client spoofing)
    payload.requester_id = user.actor_id
    payload.requester_role = user.role

    # Validate target entity
    from backend.app.approvals.schemas import ApprovalActionType
    from backend.app.models.core import AnalyticsAssets
    import uuid

    if payload.action_type != ApprovalActionType.BUILD_NEW:
        if not payload.target_entity_id or not payload.target_entity_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Target entity ID is mandatory for action '{payload.action_type.value}'.",
            )
        target_id = payload.target_entity_id.strip()
        asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == target_id).first()
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Target asset '{target_id}' not found in analytics catalog.",
            )
        payload.target_entity_id = target_id
    else:
        # BUILD_NEW does not require an existing target asset
        if not payload.target_entity_id or not payload.target_entity_id.strip():
            payload.target_entity_id = f"PROV-{uuid.uuid4().hex[:6].upper()}"

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
    search: Optional[str] = Query(None, description="Search by ID, title, requester, or target entity"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """List approval requests with pagination, status/role filters, and organizational scoping."""
    query = db.query(ApprovalRequests)

    # Scoping:
    if user.role == UserRole.REQUESTER:
        query = query.filter(ApprovalRequests.requester_id == user.actor_id)
    elif user.role == UserRole.ASSET_OWNER:
        query = query.filter(
            (ApprovalRequests.target_entity_id.in_(user.assigned_asset_ids or ["__NONE__"]))
            | (ApprovalRequests.requester_id == user.actor_id)
        )
    elif user.role == UserRole.DOMAIN_STEWARD:
        query = query.filter(
            (ApprovalRequests.required_role == UserRole.DOMAIN_STEWARD.value)
            | (ApprovalRequests.target_entity_id.in_(user.assigned_asset_ids or []))
            | (ApprovalRequests.requester_id == user.actor_id)
        )

    if status_filter and isinstance(status_filter, str):
        query = query.filter(ApprovalRequests.status == status_filter.upper())
    if required_role and isinstance(required_role, str):
        query = query.filter(ApprovalRequests.required_role == required_role.upper())
    if target_entity_type and isinstance(target_entity_type, str):
        query = query.filter(ApprovalRequests.target_entity_type == target_entity_type.lower())
    if requester_id and isinstance(requester_id, str) and user.role != UserRole.REQUESTER:
        query = query.filter(ApprovalRequests.requester_id == requester_id)
    if search and isinstance(search, str):
        s = f"%{search.strip()}%"
        query = query.filter(
            (ApprovalRequests.approval_id.ilike(s))
            | (ApprovalRequests.title.ilike(s))
            | (ApprovalRequests.target_entity_id.ilike(s))
            | (ApprovalRequests.requester_id.ilike(s))
        )

    clean_offset = offset if isinstance(offset, int) else 0
    clean_limit = limit if isinstance(limit, int) else 50

    approvals = (
        query.order_by(desc(ApprovalRequests.created_at))
        .offset(clean_offset)
        .limit(clean_limit)
        .all()
    )
    return approvals


@router.get("/summary", response_model=ApprovalQueueSummaryOut)
def get_approval_queue_summary(
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """Retrieve aggregate queue metrics across pending, approved, and rejected approvals."""
    return approval_service.get_queue_summary(db, user)


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(
    approval_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """Retrieve details for a single approval request with authorization enforcement."""
    approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found.",
        )
    # Scoping checks
    if user.role == UserRole.REQUESTER and approval.requester_id != user.actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Requesters cannot access other users' private approval submissions.",
        )
    if user.role == UserRole.ASSET_OWNER:
        is_assigned = bool(user.assigned_asset_ids and approval.target_entity_id in user.assigned_asset_ids)
        is_requester = approval.requester_id == user.actor_id
        if not (is_assigned or is_requester):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Asset Owners can only view approvals for their assigned assets.",
            )
    if user.role == UserRole.DOMAIN_STEWARD:
        is_domain_role = approval.required_role == UserRole.DOMAIN_STEWARD.value
        is_assigned = bool(user.assigned_asset_ids and approval.target_entity_id in user.assigned_asset_ids)
        is_requester = approval.requester_id == user.actor_id
        if not (is_domain_role or is_assigned or is_requester):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Domain Stewards can only view domain-scoped approvals.",
            )
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve_request(
    approval_id: str,
    payload: ApprovalDecisionPayload,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """
    Authorize and approve an active approval request.
    Enforces RBAC authority, anti-self-approval restrictions, and governance blocker safeguards.
    """
    if user.role == UserRole.REQUESTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Requesters/Analysts are not authorized to adjudicate approval decisions.",
        )
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
    user: UserContext = Depends(get_current_user),
):
    """
    Reject an approval request with a mandatory substantive reason.
    """
    if user.role == UserRole.REQUESTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Requesters/Analysts are not authorized to adjudicate approval decisions.",
        )
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

