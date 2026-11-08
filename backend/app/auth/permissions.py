"""
BIOS Enterprise Role-Based Access Control (RBAC) & Authority Matrix.
Enforces the principle of least privilege, organizational scoping, and deny-by-default access.
"""
from typing import Dict, Set, List
from backend.app.auth.schemas import UserRole, ScopeType, UserContext

# Centralized Workspace Access Matrix
WORKSPACE_PERMISSIONS: Dict[str, Set[UserRole]] = {
    # 1. Command Center: Role-specific dashboard views
    "dashboard": {
        UserRole.REQUESTER,
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 2. Analytics Intelligence: Natural language queries and requests
    "assistant": {
        UserRole.REQUESTER,
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 3. Analytics Portfolio: Asset discovery within authorized scope
    "assets": {
        UserRole.REQUESTER,
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 4. Approvals & Decisions: Role-filtered queue and tracking
    "approvals": {
        UserRole.REQUESTER,
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 5. Governance & Compliance: Findings, rules, and audit evaluations
    "governance": {
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 6. Alert Centre: Telemetry and violation alert remediations
    "alerts": {
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 7. Lifecycle Management: Migration rationalization and lifecycle oversight
    "lifecycle": {
        UserRole.ASSET_OWNER,
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 8. Development Studio: Governed Power BI artifact generation & model review
    "artifacts": {
        UserRole.DOMAIN_STEWARD,
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 9. Continuous Monitoring: Telemetry schedules and engine status
    "monitoring": {
        UserRole.BI_GOVERNANCE_REVIEWER,
        UserRole.BIOS_ADMIN,
    },
    # 10. Platform Administration: System diagnostics, ingestion, and configuration
    "admin": {
        UserRole.BIOS_ADMIN,
    },
    # 11. BI Platform Integrations: Connector credentials and synchronization
    "integrations": {
        UserRole.BIOS_ADMIN,
    },
}

# API Resource Authorizations
API_RESOURCE_PERMISSIONS: Dict[str, Set[UserRole]] = {
    # Ingestion & system admin
    "ingestion": {UserRole.BIOS_ADMIN},
    "integrations": {UserRole.BIOS_ADMIN},
    "admin": {UserRole.BIOS_ADMIN},
    # Continuous monitoring
    "monitoring": {UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    # Governed artifact studio
    "artifacts": {UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    # Lifecycle & migration
    "lifecycle": {UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    "migration": {UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    # Governance evaluation & findings
    "governance_evaluate": {UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    "governance_findings": {UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    "alerts": {UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    # Approvals & Requests (Scoping enforced at query level)
    "approvals": {UserRole.REQUESTER, UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    "assistant": {UserRole.REQUESTER, UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
    "catalog": {UserRole.REQUESTER, UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN},
}


def is_workspace_authorized(workspace: str, role: UserRole) -> bool:
    """Check if a given role is authorized to view or access a frontend workspace."""
    allowed = WORKSPACE_PERMISSIONS.get(workspace, set())
    return role in allowed


def is_api_authorized(resource: str, role: UserRole) -> bool:
    """Check if a given role has base access permission to an API resource."""
    allowed = API_RESOURCE_PERMISSIONS.get(resource, set())
    return role in allowed

