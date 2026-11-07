import pytest
from backend.app.approvals.schemas import UserRole, ApprovalActionType
from backend.app.approvals.roles import role_manager
from backend.app.approvals.service import approval_service
from backend.app.approvals.schemas import ApprovalCreate, ApprovalDecisionPayload
from backend.app.db.session import SessionLocal


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_anti_self_approval_safeguard():
    # Requester cannot approve their own submission
    allowed, msg = role_manager.can_review(
        actor_id="user_alice",
        actor_role=UserRole.BI_GOVERNANCE_REVIEWER,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER,
        action_type=ApprovalActionType.RETIRE,
        requester_id="user_alice",
    )
    assert allowed is False
    assert "Self-approval prohibited" in msg


def test_ai_agent_self_approval_ban():
    # AI agents cannot approve
    allowed, msg = role_manager.can_review(
        actor_id="DecisionAgent",
        actor_role=UserRole.BI_GOVERNANCE_REVIEWER,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER,
        action_type=ApprovalActionType.RETIRE,
        requester_id="user_bob",
    )
    assert allowed is False
    assert "AI Agent authorization prohibited" in msg


def test_role_authority_matrix():
    # ASSET_OWNER cannot approve RETIRE if required_role is BI_GOVERNANCE_REVIEWER
    allowed, msg = role_manager.can_review(
        actor_id="owner_charlie",
        actor_role=UserRole.ASSET_OWNER,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER,
        action_type=ApprovalActionType.RETIRE,
        requester_id="user_bob",
    )
    assert allowed is False
    assert "Insufficient authority" in msg

    # DOMAIN_STEWARD can review CHANGE_KPI
    allowed_kpi, _ = role_manager.can_review(
        actor_id="steward_dan",
        actor_role=UserRole.DOMAIN_STEWARD,
        required_role=UserRole.DOMAIN_STEWARD,
        action_type=ApprovalActionType.CHANGE_KPI,
        requester_id="user_bob",
    )
    assert allowed_kpi is True


def test_hard_governance_blockers_prevent_approval(db):
    # Create request with active blockers
    payload = ApprovalCreate(
        target_entity_type="asset",
        target_entity_id="AST-0074",
        action_type=ApprovalActionType.RETIRE,
        requester_id="analyst_erin",
        requester_role=UserRole.REQUESTER,
        title="Retire AST-0074",
        description="Retirement request with unresolved blockers",
        blockers=["Lineage Dependency Anchor: 3 downstream reports depend on this asset."],
    )
    req = approval_service.create_request(payload, db)

    # Attempt to approve by ASSET_OWNER should fail due to role and blockers
    with pytest.raises(Exception):
        approval_service.approve_request(
            req.approval_id,
            ApprovalDecisionPayload(
                actor_id="owner_frank",
                actor_role=UserRole.ASSET_OWNER,
                reason="Looks fine to me.",
            ),
            db,
        )

