import pytest
from backend.app.approvals.schemas import ApprovalStatus
from backend.app.approvals.state_machine import state_machine


def test_valid_approval_state_transitions():
    # DRAFT -> PENDING
    assert state_machine.can_transition(ApprovalStatus.DRAFT, ApprovalStatus.PENDING) is True
    # PENDING -> APPROVED
    assert state_machine.can_transition(ApprovalStatus.PENDING, ApprovalStatus.APPROVED) is True
    # PENDING -> REJECTED
    assert state_machine.can_transition(ApprovalStatus.PENDING, ApprovalStatus.REJECTED) is True
    # PENDING -> CHANGES_REQUESTED
    assert state_machine.can_transition(ApprovalStatus.PENDING, ApprovalStatus.CHANGES_REQUESTED) is True
    # CHANGES_REQUESTED -> PENDING (resubmission)
    assert state_machine.can_transition(ApprovalStatus.CHANGES_REQUESTED, ApprovalStatus.PENDING) is True
    # PENDING -> CANCELLED
    assert state_machine.can_transition(ApprovalStatus.PENDING, ApprovalStatus.CANCELLED) is True


def test_invalid_approval_state_transitions():
    # Cannot jump from DRAFT directly to APPROVED
    assert state_machine.can_transition(ApprovalStatus.DRAFT, ApprovalStatus.APPROVED) is False

    # Terminal states cannot transition
    assert state_machine.can_transition(ApprovalStatus.APPROVED, ApprovalStatus.PENDING) is False
    assert state_machine.can_transition(ApprovalStatus.APPROVED, ApprovalStatus.REJECTED) is False
    assert state_machine.can_transition(ApprovalStatus.REJECTED, ApprovalStatus.APPROVED) is False
    assert state_machine.can_transition(ApprovalStatus.CANCELLED, ApprovalStatus.PENDING) is False
    assert state_machine.can_transition(ApprovalStatus.EXPIRED, ApprovalStatus.APPROVED) is False

    with pytest.raises(ValueError, match="Invalid state transition"):
        state_machine.validate_transition(ApprovalStatus.APPROVED, ApprovalStatus.PENDING, "Reopen")


def test_rejection_and_changes_require_substantive_comment():
    # Valid transition with comment
    state_machine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.REJECTED, "Valid rejection reason.")
    state_machine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.CHANGES_REQUESTED, "Please clarify KPIs.")

    # Missing comment raises ValueError
    with pytest.raises(ValueError, match="Decision comment required"):
        state_machine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.REJECTED, "")

    with pytest.raises(ValueError, match="Decision comment required"):
        state_machine.validate_transition(ApprovalStatus.PENDING, ApprovalStatus.CHANGES_REQUESTED, "   ")

