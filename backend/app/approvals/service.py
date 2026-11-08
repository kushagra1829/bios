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
    def _verify_live_owner_authority(
        cls,
        db: Session,
        actor_id: str,
        actor_role: UserRole,
        approval: ApprovalRequests,
        action_name: str,
    ) -> None:
        """
        Verifies current authoritative database status of asset owners (N4 Control).
        Re-queries Owners table at execution time to catch newly deactivated owners,
        missing/forged owner records, and asset ownership scope mismatches.
        """
        if actor_role != UserRole.ASSET_OWNER:
            return

        from backend.app.models.core import Owners, AnalyticsAssets

        owner = db.query(Owners).filter(
            (Owners.owner_id == actor_id) | (Owners.owner_name == actor_id) | (Owners.email == actor_id)
        ).first()

        if not owner:
            err_msg = f"Missing or invalid owner record: Actor '{actor_id}' is not a registered asset owner in authoritative database records."
            audit_logger.record_event(
                db=db,
                actor_id=actor_id,
                actor_role=actor_role.value,
                event_type="UNAUTHORIZED_OWNER_ACTION",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action=action_name,
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        if owner.status != "active":
            err_msg = f"Inactive owner authorization prohibited: Owner '{owner.owner_id}' ({owner.owner_name}) is marked as '{owner.status}' in authoritative database records."
            audit_logger.record_event(
                db=db,
                actor_id=actor_id,
                actor_role=actor_role.value,
                event_type="UNAUTHORIZED_INACTIVE_OWNER",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action=action_name,
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        # If target is an asset and actor acts as asset owner, verify ownership scope
        if approval.target_entity_type == "asset" and actor_role == UserRole.ASSET_OWNER:
            asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == approval.target_entity_id).first()
            if asset and asset.owner_id and asset.owner_id != owner.owner_id:
                err_msg = f"Owner scope mismatch: Owner '{owner.owner_id}' does not own target asset '{asset.asset_id}' (assigned to '{asset.owner_id}')."
                audit_logger.record_event(
                    db=db,
                    actor_id=actor_id,
                    actor_role=actor_role.value,
                    event_type="OWNER_SCOPE_MISMATCH",
                    target_entity_type=approval.target_entity_type,
                    target_entity_id=approval.target_entity_id,
                    action=action_name,
                    reason=err_msg,
                )
                db.commit()
                raise PermissionError(err_msg)

    @classmethod
    def verify_waiver_synchronous(
        cls,
        db: Session,
        waiver_id: str,
        target_entity_type: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        required_action: Optional[str] = None,
    ) -> ApprovalRequests:
        """
        Synchronously verifies waiver validity at the point of use (N5 Control).
        Rejects expired waivers even if stored status in DB is still APPROVED/ACTIVE.
        Rejects revoked, invalid, out-of-scope, malformed, or RULE-008 waiver attempts.
        Records audit events on rejection.
        """
        approval = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == waiver_id).first()
        if not approval:
            err_msg = f"Waiver not found: No approval or waiver record exists for '{waiver_id}'."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="INVALID_WAIVER_VETO",
                target_entity_type=target_entity_type or "unknown",
                target_entity_id=target_entity_id or "unknown",
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise ValueError(err_msg)

        # 1. RULE-008 waiver bypass prohibition (N6 / RULE-008 Protection)
        if approval.target_entity_type == "governance_rule" and approval.target_entity_id == "RULE-008":
            err_msg = "RULE-008 Waiver Prohibited: Governance rule RULE-008 (Explainability and Evidence Grounding) cannot be waived."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="RULE_008_WAIVER_ATTEMPT_VETO",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        # 2. Check revoked or invalid status
        if approval.status in (ApprovalStatus.REJECTED.value, "REVOKED", ApprovalStatus.CHANGES_REQUESTED.value):
            err_msg = f"Invalid waiver state: Waiver '{waiver_id}' is in non-active status '{approval.status}'."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="INVALID_WAIVER_STATUS_VETO",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        # 3. Synchronous Expiration Check (even if DB status says APPROVED or ACTIVE)
        now_utc = datetime.now(timezone.utc)
        if approval.expires_at:
            exp = approval.expires_at.replace(tzinfo=timezone.utc) if approval.expires_at.tzinfo is None else approval.expires_at
            if now_utc >= exp or approval.status == ApprovalStatus.EXPIRED.value:
                approval.status = ApprovalStatus.EXPIRED.value
                approval.updated_at = now_utc
                err_msg = f"Expired waiver veto: Waiver '{waiver_id}' expired at '{exp.isoformat()}' (current time '{now_utc.isoformat()}'). Usable authorization expired."
                audit_logger.record_event(
                    db=db,
                    actor_id="SYSTEM",
                    actor_role="SYSTEM_SECURITY",
                    event_type="EXPIRED_WAIVER_USE_REJECTED",
                    target_entity_type=approval.target_entity_type,
                    target_entity_id=approval.target_entity_id,
                    action="VERIFY_WAIVER",
                    reason=err_msg,
                )
                db.commit()
                raise PermissionError(err_msg)

        # 4. Check approval state
        if approval.status != ApprovalStatus.APPROVED.value:
            err_msg = f"Waiver not approved: Waiver '{waiver_id}' is in status '{approval.status}', expected '{ApprovalStatus.APPROVED.value}'."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="UNAPPROVED_WAIVER_VETO",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        # 5. Out-of-scope check
        if target_entity_id and approval.target_entity_id and approval.target_entity_id != target_entity_id:
            err_msg = f"Out-of-scope waiver: Waiver '{waiver_id}' authorizes entity '{approval.target_entity_id}', not '{target_entity_id}'."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="OUT_OF_SCOPE_WAIVER_VETO",
                target_entity_type=approval.target_entity_type,
                target_entity_id=target_entity_id,
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

        if required_action and approval.action_type != required_action:
            err_msg = f"Waiver action mismatch: Waiver '{waiver_id}' authorizes action '{approval.action_type}', not '{required_action}'."
            audit_logger.record_event(
                db=db,
                actor_id="SYSTEM",
                actor_role="SYSTEM_SECURITY",
                event_type="WAIVER_ACTION_MISMATCH_VETO",
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action="VERIFY_WAIVER",
                reason=err_msg,
            )
            db.commit()
            raise PermissionError(err_msg)

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

        # 0. Synchronous Expiration Check (Fix N5)
        now_utc = datetime.now(timezone.utc)
        if approval.expires_at:
            exp = approval.expires_at.replace(tzinfo=timezone.utc) if approval.expires_at.tzinfo is None else approval.expires_at
            if now_utc >= exp:
                approval.status = ApprovalStatus.EXPIRED.value
                approval.updated_at = now_utc
                err_msg = f"Expired Request Veto: Approval request '{approval_id}' expired at '{exp.isoformat()}' and cannot be approved."
                audit_logger.record_event(
                    db=db,
                    actor_id=payload.actor_id,
                    actor_role=payload.actor_role.value,
                    event_type="EXPIRED_APPROVAL_ATTEMPT",
                    target_entity_type=approval.target_entity_type,
                    target_entity_id=approval.target_entity_id,
                    action=f"APPROVE_{approval.action_type}",
                    reason=err_msg,
                )
                db.commit()
                raise PermissionError(err_msg)

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
            db=db,
        )
        if not is_allowed:
            evt_type = "UNAUTHORIZED_APPROVAL_ATTEMPT"
            if "Inactive owner" in auth_msg:
                evt_type = "UNAUTHORIZED_INACTIVE_OWNER"
            elif "Missing or invalid owner" in auth_msg:
                evt_type = "UNAUTHORIZED_OWNER_ACTION"
            audit_logger.record_event(
                db=db,
                actor_id=payload.actor_id,
                actor_role=payload.actor_role.value,
                event_type=evt_type,
                target_entity_type=approval.target_entity_type,
                target_entity_id=approval.target_entity_id,
                action=f"APPROVE_{approval.action_type}",
                reason=auth_msg,
            )
            db.commit()
            raise PermissionError(auth_msg)

        # 2b. Live Inactive-Owner Verification (Fix N4)
        cls._verify_live_owner_authority(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            approval=approval,
            action_name=f"APPROVE_{approval.action_type}",
        )

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
            db=db,
        )
        if not is_allowed:
            raise PermissionError(auth_msg)

        # 2b. Live Inactive-Owner Verification (Fix N4)
        cls._verify_live_owner_authority(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            approval=approval,
            action_name=f"REJECT_{approval.action_type}",
        )

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
            db=db,
        )
        if not is_allowed:
            raise PermissionError(auth_msg)

        # Live Inactive-Owner Verification (Fix N4)
        cls._verify_live_owner_authority(
            db=db,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            approval=approval,
            action_name=f"REQUEST_CHANGES_{approval.action_type}",
        )

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
    def get_queue_summary(cls, db: Session, user: Optional[Any] = None) -> ApprovalQueueSummaryOut:
        query = db.query(ApprovalRequests)
        if user is not None:
            if getattr(user, "role", None) == UserRole.REQUESTER:
                query = query.filter(ApprovalRequests.requester_id == user.actor_id)
            elif getattr(user, "role", None) == UserRole.ASSET_OWNER:
                assigned = getattr(user, "assigned_asset_ids", []) or ["__NONE__"]
                query = query.filter(
                    (ApprovalRequests.target_entity_id.in_(assigned))
                    | (ApprovalRequests.requester_id == user.actor_id)
                )
            elif getattr(user, "role", None) == UserRole.DOMAIN_STEWARD:
                assigned = getattr(user, "assigned_asset_ids", []) or []
                query = query.filter(
                    (ApprovalRequests.required_role == UserRole.DOMAIN_STEWARD.value)
                    | (ApprovalRequests.target_entity_id.in_(assigned))
                    | (ApprovalRequests.requester_id == user.actor_id)
                )

        all_requests = query.all()

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

