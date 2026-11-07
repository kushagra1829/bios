from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VisualSpec(BaseModel):
    visual_id: str
    title: str
    visual_type: str = Field(..., description="card, line_chart, bar_chart, slicer, table")
    table_name: str
    fields: List[str] = Field(default_factory=list)
    measures: List[str] = Field(default_factory=list)
    position: Dict[str, int] = Field(default_factory=lambda: {"x": 0, "y": 0, "width": 300, "height": 200})


class PageSpec(BaseModel):
    page_id: str
    page_name: str
    display_name: str
    visuals: List[VisualSpec] = Field(default_factory=list)


class MeasureSpec(BaseModel):
    name: str
    dax_expression: str
    table_name: str
    format_string: str = "#,##0.00"
    description: Optional[str] = None
    kpi_id: Optional[str] = None


class RelationshipSpec(BaseModel):
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    is_active: bool = True
    cross_filtering_behavior: str = "oneDirection"


class DashboardSpec(BaseModel):
    spec_id: str
    title: str
    business_purpose: str
    product_scope: str
    market_scope: str
    semantic_model_id: Optional[str] = None
    request_id: Optional[str] = None
    approval_id: Optional[str] = None
    tables: List[str] = Field(default_factory=list)
    measures: List[MeasureSpec] = Field(default_factory=list)
    relationships: List[RelationshipSpec] = Field(default_factory=list)
    pages: List[PageSpec] = Field(default_factory=list)
    theme_palette: Dict[str, str] = Field(
        default_factory=lambda: {
            "primary": "#142438",      # Midnight
            "accent": "#3478F6",       # Intelligence Blue
            "success": "#16A085",      # Trust Green
            "background": "#F2F5F9",   # Cloud
            "warning": "#E5A12B",      # Warning
            "critical": "#DC5252",     # Critical
        }
    )
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    provenance_notes: Optional[str] = None


class ArtifactGenerationRequest(BaseModel):
    spec_id: Optional[str] = None
    spec: Optional[DashboardSpec] = None
    request_id: Optional[str] = None
    approval_id: Optional[str] = None
    actor_id: str = "SYSTEM_FACTORY"
    actor_role: str = "BI_GOVERNANCE_REVIEWER"
    output_format: str = "PBIP"
    force: bool = False


class ValidationCheckResult(BaseModel):
    check_name: str
    status: str = Field(..., description="PASS, FAIL, WARNING, UNVERIFIED")
    details: str


class ValidationReport(BaseModel):
    artifact_id: str
    overall_status: str = Field(..., description="VALID, INVALID, VALID_WITH_UNVERIFIED_DESKTOP")
    checks: List[ValidationCheckResult] = Field(default_factory=list)
    desktop_verification: str = "UNVERIFIED (PBIDesktop.exe not found on host)"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DashboardSpecCreate(BaseModel):
    title: str
    business_purpose: str
    product_scope: str
    market_scope: str
    semantic_model_id: Optional[str] = None
    request_id: Optional[str] = None
    approval_id: Optional[str] = None
    kpi_ids: List[str] = Field(default_factory=list)


class DashboardSpecOut(BaseModel):
    spec_id: str
    title: str
    business_purpose: str
    product_scope: str
    market_scope: str
    semantic_model_id: Optional[str] = None
    request_id: Optional[str] = None
    approval_id: Optional[str] = None
    spec_json: str
    created_by: str
    created_at: datetime


class ArtifactOut(BaseModel):
    artifact_id: str
    spec_id: str
    artifact_name: str
    format: str
    output_directory: str
    root_pbip_file: str
    status: str
    validation_status: str
    validation_report_json: Optional[str] = None
    provenance_json: str
    generated_by: str
    created_at: datetime
    validated_at: Optional[datetime] = None

