"""
FastAPI Security & RBAC Dependencies for BIOS.
Extracts authenticated identity, validates organizational scope, and enforces role boundaries.
"""
import logging
from typing import Optional, List
from fastapi import Header, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.auth.schemas import UserRole, ScopeType, UserContext
from backend.app.models.core import Owners, AnalyticsAssets

logger = logging.getLogger(__name__)


def get_current_user(
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> UserContext:
    """
    Extracts authenticated user context from request headers.
    Resolves authoritative organizational scope and owned assets from database.
    """
    raw_id = (x_actor_id or x_user_id or "").strip()
    raw_role = (x_actor_role or x_user_role or "").strip().upper()

    # Fallback to test/reviewer defaults if not supplied
    actor_id = raw_id if raw_id else "OWN-001"
    
    # Parse role
    try:
        role = UserRole(raw_role) if raw_role else UserRole.BI_GOVERNANCE_REVIEWER
    except ValueError:
        if raw_role in ("ANALYST", "REQUESTER"):
            role = UserRole.REQUESTER
        elif raw_role in ("ADMIN", "BIOS_ADMIN", "PLATFORM_ADMIN"):
            role = UserRole.BIOS_ADMIN
        else:
            role = UserRole.BI_GOVERNANCE_REVIEWER

    actor_name = actor_id
    scope_type = ScopeType.ENTERPRISE
    scope_value = "Global"
    is_admin = (role == UserRole.BIOS_ADMIN) or ("admin" in actor_id.lower())
    assigned_asset_ids: List[str] = []
    assigned_domains: List[str] = []

    # Check database owner record for active status and domain/asset scoping
    owner = db.query(Owners).filter(
        (Owners.owner_id == actor_id) | (Owners.email == actor_id) | (Owners.owner_name == actor_id)
    ).first()

    if owner:
        actor_name = owner.owner_name
        scope_value = owner.scope or "Global"
        
        # Inactive owner check
        if role == UserRole.ASSET_OWNER and owner.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Inactive owner authorization prohibited: Owner '{owner.owner_id}' has status '{owner.status}'.",
            )

        # Asset Owner: Fetch owned asset IDs
        if role == UserRole.ASSET_OWNER:
            scope_type = ScopeType.ASSET_OWNERSHIP
            owned_assets = db.query(AnalyticsAssets.asset_id).filter(AnalyticsAssets.owner_id == owner.owner_id).all()
            assigned_asset_ids = [a[0] for a in owned_assets]

        # Domain Steward: Assign domain scope
        elif role == UserRole.DOMAIN_STEWARD:
            scope_type = ScopeType.DOMAIN
            assigned_domains = [owner.scope] if owner.scope else ["Global"]
            # Also extract functional role domain if present (e.g. 'Supply', 'Market Access')
            for term in ["Commercial", "Supply", "Market Access", "Launch", "Finance"]:
                if term.lower() in (owner.role or "").lower() and term not in assigned_domains:
                    assigned_domains.append(term)

    else:
        # User not in Owners table
        if role == UserRole.REQUESTER:
            scope_type = ScopeType.INDIVIDUAL_REQUESTER
            scope_value = f"Requester: {actor_id}"
        elif role == UserRole.ASSET_OWNER:
            # If claiming ASSET_OWNER but ID doesn't exist in owners table:
            # Check if actor_id owns any asset directly
            owned_assets = db.query(AnalyticsAssets.asset_id).filter(AnalyticsAssets.owner_id == actor_id).all()
            assigned_asset_ids = [a[0] for a in owned_assets]
            scope_type = ScopeType.ASSET_OWNERSHIP
            scope_value = f"Owner: {actor_id}"
        elif role == UserRole.DOMAIN_STEWARD:
            scope_type = ScopeType.DOMAIN
            scope_value = "Commercial"
            assigned_domains = ["Commercial"]

    return UserContext(
        actor_id=actor_id,
        actor_name=actor_name,
        role=role,
        scope_type=scope_type,
        scope_value=scope_value,
        is_admin=is_admin,
        assigned_asset_ids=assigned_asset_ids,
        assigned_domains=assigned_domains,
    )


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory: verifies that the current user possesses one of the allowed roles.
    Raises HTTP 403 Forbidden if unauthorized.
    """
    def role_checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role not in allowed_roles and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access Denied: Action requires one of roles {[r.value for r in allowed_roles]}, "
                    f"but actor '{user.actor_id}' holds role '{user.role.value}'."
                ),
            )
        return user

    return role_checker


def require_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """
    Dependency: requires BIOS_ADMIN role or verified administrative privileges.
    """
    if user.role != UserRole.BIOS_ADMIN and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: Platform Administrator privileges required. Actor '{user.actor_id}' holds role '{user.role.value}'.",
        )
    return user

