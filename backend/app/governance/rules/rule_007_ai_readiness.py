from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.governance.rules.base import BaseGovernanceRule
from backend.app.governance.schemas import (
    RuleId,
    FindingSeverity,
    FindingStatus,
    TargetEntityType,
    GovernanceFindingCreate,
)
from backend.app.governance.evidence import create_evidence_reference, create_evidence_bundle
from backend.app.models.core import SemanticModels


class AiReadySemanticsRule(BaseGovernanceRule):
    """
    RULE-007 — AI-ready semantics.
    Operational requirement: Business-friendly metric names, explicit measures and clear date
    semantics should be preferred for agentic analytics.
    Detects semantic models with 'poor' or 'partial' AI readiness, specific defect patterns
    (e.g., poor_names, ambiguous_dates, implicit_measures), and refresh pipeline failures
    that prevent agentic query synthesis.
    """

    rule_id = RuleId.RULE_007
    rule_name = "AI-ready semantics"
    rule_description = "Business-friendly metric names, explicit measures and clear date semantics should be preferred for agentic analytics."
    priority = "medium"
    category = "agentic_readiness"
    target_entities = ["model"]

    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        findings: List[GovernanceFindingCreate] = []

        models = db.query(SemanticModels).all()

        for model in models:
            has_ai_flaw = model.ai_readiness in ("poor", "partial") or model.ai_issue_pattern != "clear"
            has_refresh_flaw = model.refresh_status in ("failed", "warning")

            if has_ai_flaw or has_refresh_flaw:
                # Determine severity: critical if failed refresh + poor AI readiness; high if poor; medium if partial/warning
                if model.refresh_status == "failed" and model.ai_readiness == "poor":
                    severity = FindingSeverity.CRITICAL
                elif model.ai_readiness == "poor" or model.refresh_status == "failed":
                    severity = FindingSeverity.HIGH
                else:
                    severity = FindingSeverity.MEDIUM

                primary_ref = create_evidence_reference(
                    source_table="semantic_models",
                    record_id=model.model_id,
                    field_name="ai_readiness,ai_issue_pattern",
                    observed_value=f"readiness: {model.ai_readiness}, pattern: {model.ai_issue_pattern}",
                    expected_condition="ai_readiness == 'good' AND ai_issue_pattern == 'clear'",
                    metadata={
                        "model_name": model.model_name,
                        "table_count": model.table_count,
                        "measure_count": model.measure_count,
                        "refresh_status": model.refresh_status,
                    },
                )

                corroborating = []
                if has_refresh_flaw:
                    corroborating.append(
                        create_evidence_reference(
                            source_table="semantic_models",
                            record_id=model.model_id,
                            field_name="refresh_status",
                            observed_value=model.refresh_status,
                            expected_condition="refresh_status == 'healthy'",
                            metadata={"refresh_frequency": model.refresh_frequency},
                        )
                    )

                bundle = create_evidence_bundle(
                    primary_reference=primary_ref,
                    corroborating_references=corroborating,
                    context_notes=(
                        f"Model {model.model_id} exhibits '{model.ai_issue_pattern}' pattern with "
                        f"'{model.ai_readiness}' AI readiness and '{model.refresh_status}' refresh status."
                    ),
                )

                # Formulate targeted remedial recommendation based on pattern
                if model.ai_issue_pattern == "poor_names":
                    rec = f"Rename columns and measures in {model.model_id} to business-friendly, self-describing terms."
                elif model.ai_issue_pattern == "ambiguous_dates":
                    rec = f"Establish unambiguous calendar table role-playing date relationships in {model.model_id}."
                elif model.ai_issue_pattern == "implicit_measures":
                    rec = f"Replace implicit column aggregations with explicit governed DAX measures in {model.model_id}."
                elif model.refresh_status == "failed":
                    rec = f"Repair ETL refresh failure for {model.model_id} before exposing to agentic workflows."
                else:
                    rec = f"Standardize semantic layer in {model.model_id} to satisfy agentic analytics criteria."

                findings.append(
                    GovernanceFindingCreate(
                        rule_id=self.rule_id,
                        target_entity_type=TargetEntityType.MODEL,
                        target_entity_id=model.model_id,
                        category=self.category,
                        severity=severity,
                        status=FindingStatus.OPEN,
                        title=f"AI-readiness defect: {model.model_id} ({model.ai_issue_pattern})",
                        explanation=(
                            f"Semantic model {model.model_id} ('{model.model_name}') has "
                            f"'{model.ai_readiness}' AI readiness with issue pattern '{model.ai_issue_pattern}' "
                            f"(refresh: '{model.refresh_status}'). Agentic LLMs require clean naming, explicit "
                            "measures, and reliable refresh schedules to synthesize accurate analytical answers."
                        ),
                        observed_value=f"readiness: {model.ai_readiness}, issue: {model.ai_issue_pattern}, refresh: {model.refresh_status}",
                        expected_condition="ai_readiness: 'good', pattern: 'clear', refresh: 'healthy'",
                        recommended_action=rec,
                        human_approval_required=True,
                        evidence_bundle=bundle,
                    )
                )

        return findings

