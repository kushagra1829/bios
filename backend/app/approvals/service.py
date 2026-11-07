import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.approvals.schemas import (
    ApprovalStatus,
    ApprovalActionType,
    UserRole,
    ApprovalCreate,
    ApprovalDecisionPayload,
    ApprovalQueueSummaryOut,
)
from backend.app.approvals.roles import role_manager
from backend.app.approvals.state_machine import state_machine
from backend.app.approvals.routing import routing_engine
from backend.app.approvals.audit import audit_logger
from backend.app.models.approval import (
    ApprovalRequests,
    ApprovalStateTransitions,
    AuditEvents,
)
from backend.app.models.assistant import AssistantRecommendations
from backend.app.models.lifecycle import LifecycleAssetAssessments, MigrationAssessments

logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Core human-in-the-loop approval workflow service for BIOS.
    Orchestrates approval request lifecycles, role-based authorization,
    anti-self-approval enforcement, governance blocker vetoes, and immutable audit trails.
    """

    @classmethod
    def create_request(
        cls,
        payload: ApprovalCreate,
        db: Session,
    ) -> ApprovalRequests:
        now_utc = datetime.now(timezone.utc)
        approval_id = f"APR-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Resolve required authorization role based on routing rules
        required_role = routing_engine.resolve_required_role(
            action_type=payload.action_type,
            evidence=payload.evidence_snapshot,
            blockers=payload.blockers,
        )

        expiry = now_utc + timedelta(days=payload.expiry_days or 30)

        approval = ApprovalRequests(
            approval_id=approval_id,
            target_entity_type=payload.target_entity_type,
            target_entity_id=payload.target_entity_id,
            action_type=payload.action_type.value,
            recommendation_ref=payload.recommendation_ref,
            requester_id=payload.requester_id,
            requester_role=payload.requester_role.value,
            required_role=required_role.value,
            status=ApprovalStatus.PENDING.value,
            title=payload.title,
            description=payload.description,
            evidence_snapshot_json=json.dumps(payload.evidence_snapshot),
            blockers_json=json.dumps(payload.blockers),
            warnings_json=json.dumps(payload.warnings),
            created_at=now_utc,
            updated_at=now_utc,
            expires_at=expiry,
        )
        db.add(approval)
        db.flush()

        # Initial transition DRAFT -> PENDING
        transition = ApprovalStateTransitions(
            transition_id=f"TRN-{uuid.uuid4().hex[:8].upper()}",
            approval_id=approval_id,
            from_state=ApprovalStatus.DRAFT.value,
            to_state=ApprovalStatus.PENDING.value,
            actor_id=payload.requester_id,
            actor_role=payload.requester_role.value,
            comment=f"Approval request submitted: {payload.title}",
            transitioned_at=now_utc,
        )
        db.add(transition)

        # Append immutable audit event
        audit_logger.record_event(
            db=db,
            actor_id=payload.requester_id,
            actor_role=payload.requester_role.value,
            event_type="APPROVAL_REQUESTED",
            target_entity_type=payload.target_entity_type,
            target_entity_id=payload.target_entity_id,
            action=f"REQUEST_{payload.action_type.value}",
            before_state=None,
            after_state={"status": ApprovalStatus.PENDING.value, "required_role": required_role.value},
            reason=payload.title,
            evidence_snapshot=payload.evidence_snapshot,
            associated_recommendation_id=payload.recommendation_ref,
        )

        db.commit()
        return approval

    @classmethod
    def approve_request(
        cls,
        approval_id: str,
        payload: ApprovalDecisionPayload,
        db: Session,
    ) -> ApprovalRequests:
        approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        current_status = ApprovalStatus(approval.status)
        target_status = ApprovalStatus.APPROVED

        # 1. State machine validation
        state_machine.validate_transition(current_status, target_status, payload.reason)

        # 2. RBAC & Anti-Self-Approval Authorization Check
        required_role = UserRole(approval.required_role)
        action_type = ApprovalActionType(approval.action_type)

        is_allowed, auth_msg = role_manager.can_review(
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            required_role=required_role,
            action_type=action_type,
            requester_id=approval.requester_id,
        )
        if not is_allowed:
            # Record unauthorized attempt in audit log before raising
            audit_logger.record_event(
                db=db,
                actor_id=payload.actor_id,
                actor_role=payload.actor_role.value,
                event_type="UNAUTHORIZED_APPROVAL_ATTEMPT",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action=f"APPROVE_{approval.action_type}",
                reason=auth_msg,
            )
            db.commit()
            raise PermissionError(auth_msg)

        # 3. Hard Governance Blockers Safeguard
        blockers = json.loads(approval.blockers_json or "[]")
        if blockers and action_type != ApprovalActionType.GOVERNANCE_EXCEPTION:
            if payload.actor_role != UserRole.BI_GOVERNANCE_REVIEWER:
                err_msg = (
                    f"Governance Blocker Veto: Request {approval_id} has {len(blockers)} unresolved "
                    f"governance blockers ({'; '.join(blockers[:2])}). Approval prohibited without formal "
                    "GOVERNANCE_EXCEPTION review by BI_GOVERNANCE_REVIEWER."
                )
                audit_logger.record_event(
                    db=db,
                    actor_id=payload.actor_id,
                    actor_role=payload.actor_role.value,
                    event_type="GOVERNANCE_BLOCKER_VETO",
                    target_entity_type=approval.target_entity_type,
                    target_entity_id=approval.target_entity_id,
                    action=f"APPROVE_{approval.action_type}",
                    reason=err_msg,
                )
                db.commit()
                raise ValueError(err_msg)

        now_utc = datetime.now(timezone.utc)
        before_state = {"status": approval.status}

        # Apply approval
        approval.status = target_status.value
        approval.decided_by_id = payload.actor_id
        approval.decided_by_role = payload.actor_role.value
        approval.decision_reason = payload.reason
        approval.decided_at = now_utc
        approval.updated_at = now_utc

        # Record state transition
        transition = ApprovalStateTransitions(
            transition_id=f"TRN-{uuid.uuid4().hex[:8].upper()}",
            approval_id=approval_id,
            from_state=current_status.value,
            to_state=target_status.value,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            comment=payload.reason,
            transitioned_at=now_utc,
        )
        db.add(transition)

        # Append audit event
        audit_logger.record_event(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            event_type="APPROVAL_GRANTED",
            target_entity_type=approval.target_entity_type,
            target_entity_id=approval.target_entity_id,
            action=f"APPROVE_{approval.action_type}",
            before_state=before_state,
            after_state={"status": target_status.value, "decided_by": payload.actor_id},
            reason=payload.reason,
            associated_recommendation_id=approval.recommendation_ref,
        )

        db.commit()
        return approval

    @classmethod
    def reject_request(
        cls,
        approval_id: str,
        payload: ApprovalDecisionPayload,
        db: Session,
    ) -> ApprovalRequests:
        approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        current_status = ApprovalStatus(approval.status)
        target_status = ApprovalStatus.REJECTED

        # 1. State machine validation (mandatory reason check)
        state_machine.validate_transition(current_status, target_status, payload.reason)

        # 2. RBAC check
        required_role = UserRole(approval.required_role)
        action_type = ApprovalActionType(approval.action_type)

        is_allowed, auth_msg = role_manager.can_review(
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            required_role=required_role,
            action_type=action_type,
            requester_id=approval.requester_id,
        )
        if not is_allowed:
            raise PermissionError(auth_msg)

        now_utc = datetime.now(timezone.utc)
        before_state = {"status": approval.status}

        approval.status = target_status.value
        approval.decided_by_id = payload.actor_id
        approval.decided_by_role = payload.actor_role.value
        approval.decision_reason = payload.reason
        approval.decided_at = now_utc
        approval.updated_at = now_utc

        transition = ApprovalStateTransitions(
            transition_id=f"TRN-{uuid.uuid4().hex[:8].upper()}",
            approval_id=approval_id,
            from_state=current_status.value,
            to_state=target_status.value,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            comment=payload.reason,
            transitioned_at=now_utc,
        )
        db.add(transition)

        audit_logger.record_event(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            event_type="APPROVAL_REJECTED",
            target_entity_type=approval.target_entity_type,
            target_entity_id=approval.target_entity_id,
            action=f"REJECT_{approval.action_type}",
            before_state=before_state,
            after_state={"status": target_status.value, "decided_by": payload.actor_id},
            reason=payload.reason,
            associated_recommendation_id=approval.recommendation_ref,
        )

        db.commit()
        return approval

    @classmethod
    def request_changes(
        cls,
        approval_id: str,
        payload: ApprovalDecisionPayload,
        db: Session,
    ) -> ApprovalRequests:
        approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()
        if not approval:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        current_status = ApprovalStatus(approval.status)
        target_status = ApprovalStatus.CHANGES_REQUESTED

        state_machine.validate_transition(current_status, target_status, payload.reason)

        required_role = UserRole(approval.required_role)
        action_type = ApprovalActionType(approval.action_type)

        is_allowed, auth_msg = role_manager.can_review(
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            required_role=required_role,
            action_type=action_type,
            requester_id=approval.requester_id,
        )
        if not is_allowed:
            raise PermissionError(auth_msg)

        now_utc = datetime.now(timezone.utc)
        before_state = {"status": approval.status}

        approval.status = target_status.value
        approval.decided_by_id = payload.actor_id
        approval.decided_by_role = payload.actor_role.value
        approval.decision_reason = payload.reason
        approval.decided_at = now_utc
        approval.updated_at = now_utc

        transition = ApprovalStateTransitions(
            transition_id=f"TRN-{uuid.uuid4().hex[:8].upper()}",
            approval_id=approval_id,
            from_state=current_status.value,
            to_state=target_status.value,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            comment=payload.reason,
            transitioned_at=now_utc,
        )
        db.add(transition)

        audit_logger.record_event(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role.value,
            event_type="CHANGES_REQUESTED",
            target_entity_type=approval.target_entity_type,
            target_entity_id=approval.target_entity_id,
            action=f"REQUEST_CHANGES_{approval.action_type}",
            before_state=before_state,
            after_state={"status": target_status.value, "decided_by": payload.actor_id},
            reason=payload.reason,
            associated_recommendation_id=approval.recommendation_ref,
        )

        db.commit()
        return approval

    @classmethod
    def get_queue_summary(cls, db: Session) -> ApprovalQueueSummaryOut:
        all_requests = db.query(ApprovalRequests).all()

        pending_by_role: Dict[str, int] = {}
        total_pending = 0
        total_approved = 0
        total_rejected = 0
        total_changes = 0
        total_expired = 0

        for r in all_requests:
            if r.status == ApprovalStatus.PENDING.value:
                total_pending += 1
                pending_by_role[r.required_role] = pending_by_role.get(r.required_role, 0) + 1
            elif r.status == ApprovalStatus.APPROVED.value:
                total_approved += 1
            elif r.status == ApprovalStatus.REJECTED.value:
                total_rejected += 1
            elif r.status == ApprovalStatus.CHANGES_REQUESTED.value:
                total_changes += 1
            elif r.status == ApprovalStatus.EXPIRED.value:
                total_expired += 1

        return ApprovalQueueSummaryOut(
            total_pending=total_pending,
            pending_by_role=pending_by_role,
            total_approved=total_approved,
            total_rejected=total_rejected,
            total_changes_requested=total_changes,
            expired_count=total_expired,
        )


approval_service = ApprovalService()

