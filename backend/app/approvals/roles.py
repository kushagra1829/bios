import logging
from typing import Dict, List, Set
from backend.app.approvals.schemas import UserRole, ApprovalActionType

logger = logging.getLogger(__name__)


class RolePermissionManager:
    """
    Backend role-based access control (RBAC) and authority verification for BIOS.
    Enforces principle of least privilege, segregation of duties, and self-approval bans.
    """

    # Role authority hierarchy for actions
    ROLE_ACTION_AUTHORITY: Dict[UserRole, Set[ApprovalActionType]] = {
        UserRole.BI_GOVERNANCE_REVIEWER: {
            ApprovalActionType.RETIRE,
            ApprovalActionType.CONSOLIDATE,
            ApprovalActionType.MIGRATE,
            ApprovalActionType.PUBLISH_ARTIFACT,
            ApprovalActionType.GOVERNANCE_EXCEPTION,
            ApprovalActionType.CHANGE_MODEL,
            ApprovalActionType.CHANGE_KPI,
        },
        UserRole.DOMAIN_STEWARD: {
            ApprovalActionType.CHANGE_MODEL,
            ApprovalActionType.CHANGE_KPI,
            ApprovalActionType.MIGRATE,
            ApprovalActionType.CONSOLIDATE,
        },
        UserRole.ASSET_OWNER: {
            ApprovalActionType.CONSOLIDATE,
            ApprovalActionType.PUBLISH_ARTIFACT,
        },
        UserRole.BIOS_ADMIN: {
            # Admins manage system config and lifecycle review queues, but cannot unilaterally
            # approve domain KPIs without steward review or exceptions without governance review
            ApprovalActionType.PUBLISH_ARTIFACT,
            ApprovalActionType.MIGRATE,
        },
        UserRole.REQUESTER: set(),
    }

    @classmethod
    def can_review(
        cls,
        actor_id: str,
        actor_role: UserRole,
        required_role: UserRole,
        action_type: ApprovalActionType,
        requester_id: str,
    ) -> tuple[bool, str]:
        """
        Validate whether the given actor can authorize or reject an approval request.
        Returns: (is_allowed: bool, rejection_reason: str)
        """
        # 1. Anti-Self-Approval Safeguard
        if actor_id.strip().lower() == requester_id.strip().lower():
            return False, f"Self-approval prohibited: Requester '{requester_id}' cannot approve their own submission."

        # 2. AI Agent Self-Approval Ban
        if "agent" in actor_id.lower() or "bot" in actor_id.lower() or "ai" in actor_id.lower():
            return False, f"AI Agent authorization prohibited: Actor '{actor_id}' cannot authorize approval requests."

        # 3. Exact Role Match or Higher Authority
        if actor_role == required_role:
            return True, "Role matches required authorization level."

        # BI Governance Reviewer has overarching authority across lifecycle actions
        if actor_role == UserRole.BI_GOVERNANCE_REVIEWER:
            return True, "BI Governance Reviewer possesses overarching governance authority."

        # Check action authority map
        allowed_actions = cls.ROLE_ACTION_AUTHORITY.get(actor_role, set())
        if action_type in allowed_actions and required_role != UserRole.BI_GOVERNANCE_REVIEWER:
            return True, f"Role '{actor_role}' has authorized scope for action '{action_type}'."

        return False, (
            f"Insufficient authority: Request requires role '{required_role.value}', "
            f"but actor holds role '{actor_role.value}' for action '{action_type.value}'."
        )


role_manager = RolePermissionManager()

