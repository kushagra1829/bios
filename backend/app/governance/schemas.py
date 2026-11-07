from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class RuleId(str, Enum):
    RULE_001 = "RULE-001"
    RULE_002 = "RULE-002"
    RULE_003 = "RULE-003"
    RULE_004 = "RULE-004"
    RULE_005 = "RULE-005"
    RULE_006 = "RULE-006"
    RULE_007 = "RULE-007"
    RULE_008 = "RULE-008"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(str, Enum):
    OPEN = "open"
    PERSISTING = "persisting"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class TargetEntityType(str, Enum):
    ASSET = "asset"
    MODEL = "model"
    KPI = "kpi"
    REQUEST = "request"
    SYSTEM = "system"


class EvidenceReference(BaseModel):
    source_table: str
    record_id: str
    field_name: str
    observed_value: Any
    expected_condition: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    primary_reference: EvidenceReference
    corroborating_references: List[EvidenceReference] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: bool = True
    context_notes: Optional[str] = None


class GovernanceFindingCreate(BaseModel):
    rule_id: RuleId
    target_entity_type: TargetEntityType
    target_entity_id: str
    category: str
    severity: FindingSeverity
    status: FindingStatus = FindingStatus.OPEN
    title: str
    explanation: str
    observed_value: Optional[str] = None
    expected_condition: Optional[str] = None
    recommended_action: str
    human_approval_required: bool = True
    evidence_bundle: EvidenceBundle
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GovernanceFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: str
    run_id: str
    rule_id: str
    target_entity_type: str
    target_entity_id: str
    category: str
    severity: str
    status: str
    title: str
    explanation: str
    observed_value: Optional[str] = None
    expected_condition: Optional[str] = None
    recommended_action: str
    human_approval_required: bool
    evidence_json: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None


class EvaluationRunSummary(BaseModel):
    run_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    total_findings: int
    findings_by_rule: Dict[str, int]
    findings_by_severity: Dict[str, int]
    findings_by_status: Dict[str, int]
    execution_time_ms: float


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    summary_json: Optional[str] = None


class GovernanceRuleInfo(BaseModel):
    rule_id: str
    rule_name: str
    rule_description: str
    priority: str
    category: str
    target_entities: List[str]
    thresholds: Dict[str, Any]

