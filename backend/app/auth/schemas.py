"""
BIOS Enterprise RBAC & Security Schemas.
Defines organizational roles, access scopes, and security context.
"""
from enum import Enum
from typing import List, Optional, Set
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    BIOS_ADMIN = "BIOS_ADMIN"
    BI_GOVERNANCE_REVIEWER = "BI_GOVERNANCE_REVIEWER"
    DOMAIN_STEWARD = "DOMAIN_STEWARD"
    ASSET_OWNER = "ASSET_OWNER"
    REQUESTER = "REQUESTER"


class ScopeType(str, Enum):
    ENTERPRISE = "ENTERPRISE"
    DOMAIN = "DOMAIN"
    ASSET_OWNERSHIP = "ASSET_OWNERSHIP"
    INDIVIDUAL_REQUESTER = "INDIVIDUAL_REQUESTER"


class UserContext(BaseModel):
    """
    Authenticated security context for an active user session.
    Carries verified identity, role, scope, and entity boundaries.
    """
    actor_id: str = Field(description="Unique identity of the user/actor")
    actor_name: str = Field(description="Display name or email of the user")
    role: UserRole = Field(description="Assigned organizational role")
    scope_type: ScopeType = Field(description="Organizational authority boundary")
    scope_value: str = Field(default="Global", description="Specific domain, region, or ownership boundary")
    is_admin: bool = Field(default=False, description="Flag for platform administration privileges")
    assigned_asset_ids: List[str] = Field(default_factory=list, description="Explicit list of owned assets for Asset Owners")
    assigned_domains: List[str] = Field(default_factory=list, description="Explicit list of product/regional domains for Stewards")
    delegated_authorities: Set[str] = Field(default_factory=set, description="Explicitly granted approval/action authorities")

