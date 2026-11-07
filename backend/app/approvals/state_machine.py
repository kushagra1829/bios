import logging
from typing import Dict, Set
from backend.app.approvals.schemas import ApprovalStatus

logger = logging.getLogger(__name__)


class ApprovalStateMachine:
    """
    Deterministic finite state machine for human approvals.
    Enforces valid transitions and rejects unauthorized or out-of-order state modifications.
    """

    VALID_TRANSITIONS: Dict[ApprovalStatus, Set[ApprovalStatus]] = {
        ApprovalStatus.DRAFT: {
            ApprovalStatus.PENDING,
            ApprovalStatus.CANCELLED,
        },
        ApprovalStatus.PENDING: {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CHANGES_REQUESTED,
            ApprovalStatus.CANCELLED,
            ApprovalStatus.EXPIRED,
        },
        ApprovalStatus.CHANGES_REQUESTED: {
            ApprovalStatus.PENDING,  # Resubmission after changes
            ApprovalStatus.CANCELLED,
        },
        # Terminal states have no valid onward transitions
        ApprovalStatus.APPROVED: set(),
        ApprovalStatus.REJECTED: set(),
        ApprovalStatus.CANCELLED: set(),
        ApprovalStatus.EXPIRED: set(),
    }

    @classmethod
    def can_transition(cls, from_state: ApprovalStatus, to_state: ApprovalStatus) -> bool:
        allowed = cls.VALID_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @classmethod
    def validate_transition(cls, from_state: ApprovalStatus, to_state: ApprovalStatus, reason: str) -> None:
        if not cls.can_transition(from_state, to_state):
            raise ValueError(
                f"Invalid state transition: Cannot transition approval request from '{from_state.value}' "
                f"to '{to_state.value}'. Permitted transitions from '{from_state.value}': "
                f"{[s.value for s in cls.VALID_TRANSITIONS.get(from_state, set())]}."
            )

        if to_state in (ApprovalStatus.REJECTED, ApprovalStatus.CHANGES_REQUESTED):
            if not reason or len(reason.strip()) < 5:
                raise ValueError(
                    f"Decision comment required: Transitioning to '{to_state.value}' requires a substantive "
                    "justification (minimum 5 characters)."
                )


state_machine = ApprovalStateMachine()

