from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ApprovalActionType(str, Enum):
    RETIRE = "RETIRE"
    CONSOLIDATE = "CONSOLIDATE"
    MIGRATE = "MIGRATE"
    CHANGE_MODEL = "CHANGE_MODEL"
    CHANGE_KPI = "CHANGE_KPI"
    PUBLISH_ARTIFACT = "PUBLISH_ARTIFACT"
    GOVERNANCE_EXCEPTION = "GOVERNANCE_EXCEPTION"


class UserRole(str, Enum):
    BIOS_ADMIN = "BIOS_ADMIN"
    BI_GOVERNANCE_REVIEWER = "BI_GOVERNANCE_REVIEWER"
    ASSET_OWNER = "ASSET_OWNER"
    DOMAIN_STEWARD = "DOMAIN_STEWARD"
    REQUESTER = "REQUESTER"


class ApprovalCreate(BaseModel):
    target_entity_type: str = Field(description="Entity type: asset, model, kpi, artifact, migration")
    target_entity_id: str = Field(description="Unique entity ID (e.g. AST-0001, SM-001, KPI-001)")
    action_type: ApprovalActionType = Field(description="Consequential action requested")
    recommendation_ref: Optional[str] = Field(None, description="Associated recommendation (e.g. REC-xxx, ASM-xxx, MIG-xxx)")
    requester_id: str = Field(min_length=2, description="Identity of the requester")
    requester_role: UserRole = Field(default=UserRole.REQUESTER)
    title: str = Field(min_length=5, description="Summary title of the approval request")
    description: str = Field(min_length=10, description="Detailed rationale and scope")
    evidence_snapshot: Dict[str, Any] = Field(default_factory=dict)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    expiry_days: Optional[int] = Field(default=30, ge=1, le=365)


class ApprovalDecisionPayload(BaseModel):
    actor_id: str = Field(min_length=2, description="Reviewer identity")
    actor_role: UserRole = Field(description="Reviewer role")
    reason: str = Field(min_length=5, description="Mandatory decision reason/rationale")


class ApprovalTransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transition_id: str
    approval_id: str
    from_state: str
    to_state: str
    actor_id: str
    actor_role: str
    comment: Optional[str] = None
    transitioned_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    target_entity_type: str
    target_entity_id: str
    action_type: str
    recommendation_ref: Optional[str] = None
    requester_id: str
    requester_role: str
    required_role: str
    status: str
    title: str
    description: str
    evidence_snapshot_json: Optional[str] = None
    blockers_json: Optional[str] = None
    warnings_json: Optional[str] = None
    decision_reason: Optional[str] = None
    decided_by_id: Optional[str] = None
    decided_by_role: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    actor_id: str
    actor_role: str
    event_type: str
    target_entity_type: str
    target_entity_id: str
    action: str
    before_state_json: Optional[str] = None
    after_state_json: Optional[str] = None
    reason: Optional[str] = None
    evidence_snapshot_json: Optional[str] = None
    associated_recommendation_id: Optional[str] = None
    provenance_json: Optional[str] = None
    created_at: datetime


class ApprovalQueueSummaryOut(BaseModel):
    total_pending: int
    pending_by_role: Dict[str, int]
    total_approved: int
    total_rejected: int
    total_changes_requested: int
    expired_count: int

