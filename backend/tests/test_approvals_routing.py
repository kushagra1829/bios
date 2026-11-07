from backend.app.approvals.schemas import ApprovalActionType, UserRole
from backend.app.approvals.routing import routing_engine


def test_routing_retire_with_downstream_dependents():
    # Asset with downstream dependents requires BI_GOVERNANCE_REVIEWER
    role = routing_engine.resolve_required_role(
        action_type=ApprovalActionType.RETIRE,
        evidence={"lineage": {"downstream_dependent_count": 2}},
    )
    assert role == UserRole.BI_GOVERNANCE_REVIEWER


def test_routing_retire_unendorsed_without_dependents():
    # Unendorsed asset with 0 dependents can be reviewed by ASSET_OWNER
    role = routing_engine.resolve_required_role(
        action_type=ApprovalActionType.RETIRE,
        evidence={"endorsement": "none", "lineage": {"downstream_dependent_count": 0}, "reach": {"estimated_audience": 50}},
    )
    assert role == UserRole.ASSET_OWNER


def test_routing_governance_exception():
    # Governance exceptions strictly require BI_GOVERNANCE_REVIEWER
    role = routing_engine.resolve_required_role(
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION,
    )
    assert role == UserRole.BI_GOVERNANCE_REVIEWER


def test_routing_kpi_and_model_changes():
    # Metric and model changes route to DOMAIN_STEWARD
    role_kpi = routing_engine.resolve_required_role(action_type=ApprovalActionType.CHANGE_KPI)
    role_model = routing_engine.resolve_required_role(action_type=ApprovalActionType.CHANGE_MODEL)

    assert role_kpi == UserRole.DOMAIN_STEWARD
    assert role_model == UserRole.DOMAIN_STEWARD


def test_routing_migration_high_complexity():
    # High complexity migration routes to BI_GOVERNANCE_REVIEWER
    role = routing_engine.resolve_required_role(
        action_type=ApprovalActionType.MIGRATE,
        evidence={"complexity": "high"},
    )
    assert role == UserRole.BI_GOVERNANCE_REVIEWER

