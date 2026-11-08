"""
Business-facing presentation of an assistant response.

It changes no decision: it only reorganises what the agents produced into the response standard
(docs/AI/BIOS_RESPONSE_STANDARD.md) - answer first, evidence and next steps next, governance last -
and deduplicates governance findings so the same control is shown once. The exact backend counts
are kept beside the displayed counts so nothing is silently hidden.
"""
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    ActionStatus,
    AssistantPresentation,
    BusinessIntent,
    DataAnswer,
    DecisionResult,
    DecisionType,
    DiscoveryResult,
    DuplicationResult,
    FindingView,
    GovernanceAgentResult,
    GovernanceAnswer,
    GovernancePresentation,
    KpiAnalysisResult,
    MigrationAnswer,
    RequestType,
)
from backend.app.models.governance import GovernanceFindings

RULE_ID = re.compile(r"\bRULE-\d{3}\b")
ENTITY_ID = re.compile(r"\b(?:AST|SM)-\d{3,4}\b")
KPI_ID = re.compile(r"\bKPI-\d{3}\b")
SEVERITY_RANK = {"CRITICAL": 0, "BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4, "DIRECTIVE": 5}

ACTION_LABELS = {
    "REUSE": "Reuse an existing asset",
    "CONSOLIDATE": "Consolidate overlapping assets",
    "MODIFY": "Modify an existing asset",
    "MIGRATE": "Migrate a legacy asset",
    "RETIRE": "Retire an asset",
    "BUILD_NEW": "Build a new asset",
    "NEEDS_CLARIFICATION": "Clarification needed",
    "INFORMATIONAL": "Answer",
}
STATUS_LABELS = {
    "ACTIONABLE": "Can proceed",
    "REQUIRES_APPROVAL": "Requires human approval",
    "BLOCKED": "Blocked by governance",
    "NEEDS_INPUT": "Waiting for your input",
    "NOT_APPLICABLE": "No action proposed",
}

# Short, business-readable explanations, keyed by (rule, control).
CONTROL_MESSAGES = {
    ("RULE-003", "owner_missing"): "No accountable owner is assigned. The asset cannot be safely extended until ownership is established.",
    ("RULE-003", "owner_inactive"): "The assigned owner is inactive. Changes need an active owner's approval; reassign first.",
    ("RULE-003", "target_blocked"): "Using this asset as the target is blocked pending owner assignment.",
}


def _control(rule_id: str, text: str) -> str:
    lowered = text.lower()
    if rule_id == "RULE-003":
        if "target" in lowered and ("blocked" in lowered or "ineligible" in lowered):
            return "target_blocked"
        if "inactive" in lowered:
            return "owner_inactive"
        return "owner_missing"
    if rule_id == "RULE-001":
        return "reuse_directive" if "directive" in lowered or "already serves" in lowered else "duplicate_title"
    if rule_id == "RULE-002":
        kpi = KPI_ID.search(text)
        return f"kpi:{kpi.group(0)}" if kpi else "non_canonical_kpis"
    return "finding"


def _severity_of(text: str, default: str) -> str:
    upper = text.upper()
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        if level in upper:
            return level
    return default


def build_governance(
    governance: GovernanceAgentResult,
    decision: DecisionResult,
    db: Session,
    extra_findings: Optional[List[FindingView]] = None,
) -> GovernancePresentation:
    """Deduplicate the Governance and Decision agents' strings into one FindingView per control."""
    targets = set(decision.target_asset_ids)
    db_findings: Dict[Tuple[str, str], GovernanceFindings] = {}
    ids = set(governance.request_finding_ids)
    if ids:
        for f in db.query(GovernanceFindings).filter(GovernanceFindings.finding_id.in_(list(ids))).all():
            db_findings[(f.rule_id, f.target_entity_id)] = f

    merged: Dict[Tuple[str, str, str, str], FindingView] = {}

    def add(text: str, kind: str) -> None:
        rule_match = RULE_ID.search(text)
        if not rule_match:
            rule_id = "SECURITY" if "SECURITY" in text.upper() else "GOVERNANCE"
        else:
            rule_id = rule_match.group(0)
        entity_match = ENTITY_ID.search(text) or KPI_ID.search(text)
        entity = entity_match.group(0) if entity_match else ""
        control = _control(rule_id, text)
        if kind == "WARNING" and ("DIRECTIVE" in text.upper()):
            kind = "DIRECTIVE"
        key = (kind, rule_id, entity, control)
        if key in merged:
            merged[key].sources.append(text)
            return
        finding = db_findings.get((rule_id, entity))
        severity = (finding.severity.upper() if finding else _severity_of(text, "CRITICAL" if kind == "BLOCKER" else "HIGH"))
        if kind == "DIRECTIVE":
            severity = "DIRECTIVE"
            if targets and entity and entity not in targets and decision.decision.value in ("REUSE", "MODIFY", "CONSOLIDATE"):
                text = (
                    f"RULE-001: Existing endorsed assets already serve this scope (for example {entity}). Reuse before build: "
                    f"BIOS recommends {', '.join(sorted(targets))} because it carries the strongest evidence for this request."
                )
        message = CONTROL_MESSAGES.get((rule_id, control)) or _clean(finding.title if (finding and kind != "DIRECTIVE") else text)
        effect = "PREVENTS_ACTION" if kind == "BLOCKER" else ("INFORMATIONAL" if kind == "DIRECTIVE" else "REQUIRES_REVIEW")
        if kind == "BLOCKER" and entity and entity.startswith(("AST", "SM")) and entity not in targets:
            message += f" {entity} is therefore not used as a target for this request."
        merged[key] = FindingView(
            rule_id=rule_id,
            severity=severity,
            asset_id=entity or None,
            kind=kind,
            effect=effect,
            message=message,
            required_action=(finding.recommended_action or "") if finding else "",
            finding_ids=[finding.finding_id] if finding else [],
            sources=[text],
            affects_target=bool(entity and entity in targets) or not entity,
        )

    for text in decision.blockers:
        add(text, "BLOCKER")
    for text in decision.warnings:
        add(text, "WARNING")
    for item in decision.ineligible_targets:
        for reason in item.get("reasons", []):
            rule = RULE_ID.search(reason)
            rule_id = rule.group(0) if rule else "GOVERNANCE"
            key = ("BLOCKER", rule_id, item["asset_id"], "target_blocked")
            if key not in merged:
                merged[key] = FindingView(
                    rule_id=rule_id, severity="CRITICAL", asset_id=item["asset_id"], kind="BLOCKER", effect="PREVENTS_ACTION",
                    message=(CONTROL_MESSAGES[("RULE-003", "target_blocked")] if rule_id == "RULE-003" else _clean(reason)),
                    required_action="Assign and verify an accountable owner, then ask BIOS to re-evaluate." if rule_id == "RULE-003" else "Resolve the finding, then re-evaluate.",
                    sources=[reason], affects_target=True,
                )
    for view in extra_findings or []:
        key = (view.kind, view.rule_id, view.asset_id or "", _control(view.rule_id, view.message))
        if key not in merged:
            merged[key] = view

    def order(v: FindingView):
        return (0 if v.affects_target else 1, SEVERITY_RANK.get(v.severity, 9), v.rule_id, v.asset_id or "")

    views = sorted(merged.values(), key=order)
    blockers = [v for v in views if v.kind == "BLOCKER"]
    warnings = [v for v in views if v.kind == "WARNING"]
    directives = [v for v in views if v.kind == "DIRECTIVE"]
    return GovernancePresentation(
        blockers=blockers,
        warnings=warnings,
        directives=directives,
        backend_blocker_count=len(decision.blockers),
        backend_warning_count=len(decision.warnings),
        displayed_blocker_count=len(blockers),
        displayed_warning_count=len(warnings),
        displayed_directive_count=len(directives),
        out_of_scope_count=len(governance.out_of_scope_finding_ids),
    )


def _clean(text: str) -> str:
    """Drop the rule/severity prefix the agents add; the UI shows them as labels."""
    text = re.sub(r"^\s*(?:SECURITY\s+)?(?:RULE-\d{3}\s+)?(?:HIGH\s+|CRITICAL\s+|MEDIUM\s+)?(?:BLOCKER|WARNING|DIRECTIVE)(?:\s+on\s+(?:AST|SM)-\d+)?\s*:\s*", "", text)
    text = re.sub(r"\s*Rationale:.*$", "", text)
    return text.strip().rstrip(".") + "."


def _asset_card(asset, discovery: DiscoveryResult) -> Dict:
    return {
        "asset_id": asset.asset_id,
        "asset_name": asset.asset_name,
        "product_scope": asset.product_scope,
        "market_scope": asset.market_scope,
        "platform": asset.platform,
        "endorsement": asset.endorsement,
        "lifecycle_status": asset.lifecycle_status,
        "owner_name": asset.owner_name,
        "match_tier": asset.match_tier.value if hasattr(asset.match_tier, "value") else str(asset.match_tier),
        "reasons": asset.match_reasons[:4],
    }


def _evidence_strength(decision: DecisionResult) -> str:
    """Replace an uncalibrated percentage with what the evidence actually is."""
    if decision.decision == DecisionType.INFORMATIONAL:
        return "Computed directly from source records; no estimate involved."
    if decision.decision == DecisionType.NEEDS_CLARIFICATION:
        return "Not enough information to recommend an action."
    if decision.action_status == ActionStatus.BLOCKED:
        return "The recommendation is constrained by a deterministic governance blocker."
    return (
        f"Rule-based decision (internal score {decision.confidence:.2f}). The score orders the decision matrix's outcomes; "
        "it is not a calibrated probability."
    )


def format_figure(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "M EUR":
        sign = "-" if value < 0 else ""
        return f"{sign}€{abs(value):,.2f}M"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "weeks":
        return f"{value:.1f} weeks"
    if unit == "units":
        return f"{int(round(value)):,} units"
    return f"{value} {unit}".strip()


def build_presentation(
    intent: BusinessIntent,
    discovery: DiscoveryResult,
    kpi_analysis: KpiAnalysisResult,
    duplication: DuplicationResult,
    governance: GovernanceAgentResult,
    decision: DecisionResult,
    data_answer: Optional[DataAnswer],
    governance_answer: Optional[GovernanceAnswer],
    migration_answer: Optional[MigrationAnswer],
    db: Session,
) -> AssistantPresentation:
    types = intent.request_types or [RequestType.ASSET_REQUEST]
    primary = types[0]
    asset_requested = RequestType.ASSET_REQUEST in types
    why: List[str] = []
    next_steps: List[str] = list(decision.next_steps)
    direct: List[str] = []
    matching: List[Dict] = []
    extra_findings: List[FindingView] = []

    if data_answer is not None:
        direct.append(data_answer.headline)
        if data_answer.comparison:
            direct.append(data_answer.comparison)
        for fig in data_answer.figures[:6]:
            why.append(f"{fig.label}: {format_figure(fig.value, fig.unit)}{(' — ' + fig.detail) if fig.detail else ''}")
        cov = data_answer.coverage
        if cov.records_used or cov.records_expected:
            why.append(
                f"Coverage: {cov.records_used} of {cov.records_expected} expected product-market-month records"
                + (f"; months with no data: {len(cov.months_missing_in_requested_range)}" if cov.months_missing_in_requested_range else "")
                + (f"; record labels {', '.join(f'{k} ×{v}' for k, v in sorted(cov.value_type_counts.items()))}" if cov.value_type_counts else "")
                + "."
            )
        if data_answer.unit:
            why.append(f"Units: {data_answer.unit}. Aggregation: {data_answer.aggregation or 'n/a'}.")
        why.append(f"Source: {data_answer.source.get('sheet', 'Product_Market_Monthly')} (synthetic SinceAI data, {cov.dataset_period}).")
        next_steps = list(data_answer.clarification) + ([] if not asset_requested else next_steps)
        for caveat in data_answer.caveats:
            extra_findings.append(FindingView(rule_id="DATA", severity="INFO", kind="WARNING", effect="INFORMATIONAL", message=caveat, affects_target=False))
        if kpi_analysis.canonical_approved_kpi_ids and data_answer.status in ("ANSWERED", "PARTIAL"):
            extra_findings.append(FindingView(
                rule_id="RULE-002", severity="DIRECTIVE", kind="DIRECTIVE", effect="INFORMATIONAL",
                message=f"Use the approved canonical KPI(s) {', '.join(kpi_analysis.canonical_approved_kpi_ids)} when reporting these figures.",
                affects_target=False,
            ))

    if governance_answer is not None:
        direct.append(governance_answer.headline)
        why.extend(governance_answer.explanation)
        matching.extend(governance_answer.assets[:10])
        if governance_answer.total_matching > len(governance_answer.assets):
            why.append(f"Showing {len(governance_answer.assets)} of {governance_answer.total_matching} matching records.")
        extra_findings.extend(governance_answer.findings)

    if decision.decision != DecisionType.INFORMATIONAL and not asset_requested and primary == RequestType.MIGRATION_QUESTION:
        direct.append(decision.primary_recommendation)
        why.append(decision.rationale)
    if migration_answer is not None:
        direct.append(migration_answer.headline)
        why.extend(migration_answer.explanation)
        for path, rows in migration_answer.groups.items():
            for row in rows[:6]:
                matching.append({**row, "group": path})
        if migration_answer.approval_note:
            next_steps.append(migration_answer.approval_note)

    if asset_requested:
        text = decision.primary_recommendation
        if data_answer is not None:
            text = f"On the dashboard question: {text}"
        direct.append(text)
        if decision.decision != DecisionType.NEEDS_CLARIFICATION or intent.duplication_question:
            why.append(decision.rationale)
        if decision.llm_narrative:
            why.append(f"Plain-language summary (AI-drafted, validated against the decision): {decision.llm_narrative}")
        for item in decision.ineligible_targets:
            if all(reason in decision.rationale for reason in item.get("reasons", [])):
                continue  # already stated in the rationale
            why.append(f"Not eligible as a target: {item['asset_id']} — {' '.join(item.get('reasons', []))}")
        for target in decision.target_asset_ids:
            asset = next((a for a in discovery.exact_matches + discovery.partial_matches if a.asset_id == target), None)
            if asset is not None:
                matching.insert(0, _asset_card(asset, discovery))
        shown = {m.get("asset_id") for m in matching}
        for asset in (discovery.exact_matches + discovery.partial_matches)[:6]:
            if asset.asset_id not in shown:
                matching.append(_asset_card(asset, discovery))
                shown.add(asset.asset_id)
        if duplication.explanation and decision.decision in (DecisionType.CONSOLIDATE, DecisionType.NEEDS_CLARIFICATION) and intent.duplication_question:
            why.append(duplication.explanation)

    if primary in (RequestType.DATA_QUESTION, RequestType.BUSINESS_DATA_QUESTION) and not asset_requested:
        response_type = "DATA_ANSWER" if data_answer and data_answer.status in ("ANSWERED", "PARTIAL", "NO_DATA") else "CLARIFICATION"
    elif primary == RequestType.GOVERNANCE_QUESTION and not asset_requested:
        response_type = "GOVERNANCE_ANSWER"
    elif primary == RequestType.MIGRATION_QUESTION and not asset_requested:
        response_type = "MIGRATION_RECOMMENDATION"
    elif decision.decision == DecisionType.NEEDS_CLARIFICATION:
        response_type = "CLARIFICATION"
    else:
        response_type = "ASSET_RECOMMENDATION"
    if primary in (RequestType.DATA_QUESTION, RequestType.BUSINESS_DATA_QUESTION) and asset_requested:
        response_type = "DATA_ANSWER"

    governance_view = build_governance(governance, decision, db, extra_findings)
    approval = decision.human_approval_required
    approval_text = (
        "An authorised human must approve this action before anything changes (owner authority is checked by the approvals service)."
        if approval
        else ("No approval is needed: nothing is being changed." if decision.decision in (DecisionType.INFORMATIONAL, DecisionType.NEEDS_CLARIFICATION) else
              "No change management is needed: this grants access to an existing endorsed asset.")
    )
    if decision.action_status == ActionStatus.BLOCKED:
        approval_text = "Blocked: approval can't be requested until the governance blockers below are resolved."

    return AssistantPresentation(
        response_type=response_type,
        recommended_action=decision.decision.value,
        action_label=ACTION_LABELS.get(decision.decision.value, decision.decision.value),
        action_status=decision.action_status.value,
        direct_answer=" ".join(dict.fromkeys(p for p in direct if p)),
        why=list(dict.fromkeys(w for w in why if w)),
        matching_assets=matching[:12],
        next_steps=list(dict.fromkeys(s for s in next_steps if s)),
        human_approval_required=approval,
        approval_explanation=approval_text,
        confidence_explanation=_evidence_strength(decision),
        governance=governance_view,
    )
