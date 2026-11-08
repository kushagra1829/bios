"""
BIOS Auth & Security Package.
"""
from backend.app.auth.schemas import UserRole, ScopeType, UserContext
from backend.app.auth.permissions import (
    WORKSPACE_PERMISSIONS,
    API_RESOURCE_PERMISSIONS,
    is_workspace_authorized,
    is_api_authorized,
)
from backend.app.auth.dependencies import (
    get_current_user,
    require_role,
    require_admin,
)

__all__ = [
    "UserRole",
    "ScopeType",
    "UserContext",
    "WORKSPACE_PERMISSIONS",
    "API_RESOURCE_PERMISSIONS",
    "is_workspace_authorized",
    "is_api_authorized",
    "get_current_user",
    "require_role",
    "require_admin",
]

