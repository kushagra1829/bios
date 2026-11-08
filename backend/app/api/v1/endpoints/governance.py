from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.governance.engine import engine
from backend.app.governance.registry import registry
from backend.app.governance.schemas import (
    EvaluationRunSummary,
    GovernanceFindingOut,
    GovernanceRuleInfo,
    RuleId,
)
from backend.app.models.governance import GovernanceFindings, GovernanceEvaluationRuns
from backend.app.auth.dependencies import require_role, get_current_user
from backend.app.auth.schemas import UserRole, UserContext

router = APIRouter()


@router.post("/evaluate", response_model=EvaluationRunSummary, status_code=status.HTTP_200_OK)
def trigger_evaluation(
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """
    Execute a full deterministic governance evaluation run across all eight rules.
    Persists evaluation results and tracks finding lifecycles (open, persisting, resolved).
    """
    try:
        summary = engine.evaluate_all(db)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Governance evaluation failed: {str(e)}",
        )


@router.get("/findings", response_model=List[GovernanceFindingOut])
def list_findings(
    rule_id: Optional[str] = Query(None, description="Filter by rule ID (e.g. RULE-001)"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low, info)"),
    status: Optional[str] = Query(None, description="Filter by status (open, persisting, resolved, acknowledged)"),
    target_entity_type: Optional[str] = Query(None, description="Filter by entity type (asset, model, kpi, request)"),
    target_entity_id: Optional[str] = Query(None, description="Filter by entity ID (e.g. AST-0001, SM-009)"),
    run_id: Optional[str] = Query(None, description="Filter by evaluation run ID"),
    limit: int = Query(100, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_role(UserRole.ASSET_OWNER, UserRole.DOMAIN_STEWARD, UserRole.BI_GOVERNANCE_REVIEWER, UserRole.BIOS_ADMIN)),
):
    """
    List governance findings with optional filtering by rule, severity, status, entity, or run.
    Scopes results to owned assets when queried by an Asset Owner.
    """
    query = db.query(GovernanceFindings)

    # Scoping: Asset Owner only sees findings affecting assigned assets
    if user.role == UserRole.ASSET_OWNER and user.assigned_asset_ids:
        query = query.filter(GovernanceFindings.target_entity_id.in_(user.assigned_asset_ids))

    if rule_id:
        query = query.filter(GovernanceFindings.rule_id == rule_id)
    if severity:
        query = query.filter(GovernanceFindings.severity == severity.lower())
    if status:
        query = query.filter(GovernanceFindings.status == status.lower())
    if target_entity_type:
        query = query.filter(GovernanceFindings.target_entity_type == target_entity_type.lower())
    if target_entity_id:
        query = query.filter(GovernanceFindings.target_entity_id == target_entity_id)
    if run_id:
        query = query.filter(GovernanceFindings.run_id == run_id)

    findings = (
        query.order_by(
            # Order critical first, then high
            GovernanceFindings.detected_at.desc(),
            GovernanceFindings.finding_id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return findings


@router.get("/findings/{finding_id}", response_model=GovernanceFindingOut)
def get_finding(
    finding_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetch a single governance finding by its deterministic finding ID.
    """
    finding = db.query(GovernanceFindings).filter(GovernanceFindings.finding_id == finding_id).first()
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Governance finding '{finding_id}' not found.",
        )
    return finding


@router.get("/summary")
def get_governance_summary(
    db: Session = Depends(get_db),
):
    """
    Aggregate real-time metrics across active and resolved findings, severities, and rules.
    """
    return engine.get_summary(db)


@router.get("/rules", response_model=List[GovernanceRuleInfo])
def list_governance_rules():
    """
    List all eight registered official Bayer governance rules and their thresholds.
    """
    return registry.get_all_infos()


@router.get("/rules/{rule_id}", response_model=GovernanceRuleInfo)
def get_governance_rule(rule_id: str):
    """
    Get detailed specification and thresholds for a single governance rule.
    """
    rule = registry.get(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found. Available rules: RULE-001 through RULE-008.",
        )
    return rule.get_info()

