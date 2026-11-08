"""
Mandatory deterministic validation of the final decision, for every LLM provider.

Pipeline position:
    intent -> discovery -> KPI -> duplication -> governance -> decision (+ optional LLM narrative)
    -> validate_final_decision()  <- this module
    -> API response -> presentation

The Decision Agent already selects eligible targets. This layer does not trust that: it re-derives
eligibility from the catalog and the persisted governance findings and corrects any decision that
would act on a prohibited target, whatever produced it (current logic, legacy logic, a future change
or an LLM). It never picks a new target on its own - an unvetted substitute would be a silent change -
it blocks instead and says why. It also drops any LLM narrative that contradicts the validated outcome.

Rules enforced (BIOS 1.0 release requirements):
  1. A target must exist in the catalog.
  2. No unowned asset, inactive-owner asset (for change actions) or asset with a critical finding may
     be an actionable target (answering/eligibility.py).
  3. A blocker that names a target, or a request-level blocker, makes the action BLOCKED.
  4. A blocked action has no actionable target and still requires human approval to proceed later;
     approval never overrides a blocker.
  5. Consequential actions always require human approval.
  6. The narrative may not name a rejected target unless it says it is blocked, may not claim an
     action can proceed when it is blocked, and may not cite unknown IDs.
"""
import re
from typing import List

from sqlalchemy.orm import Session

from backend.app.agents.answering.eligibility import check_target
from backend.app.agents.schemas import ActionStatus, DecisionResult, DecisionType
from backend.app.models.core import AnalyticsAssets, SemanticModels

TARGETED = {DecisionType.REUSE, DecisionType.CONSOLIDATE, DecisionType.MODIFY, DecisionType.MIGRATE, DecisionType.RETIRE}
CONSEQUENTIAL = {DecisionType.CONSOLIDATE, DecisionType.MODIFY, DecisionType.MIGRATE, DecisionType.RETIRE, DecisionType.BUILD_NEW}
ENTITY_ID = re.compile(r"\b(?:AST|SM)-\d{3,4}\b")
ACTION_VERBS = re.compile(r"\b(?:consolidat\w*|reus\w*|extend\w*|modif\w*|migrat\w*|retir\w*|build\w*|use|merge|target)\b", re.IGNORECASE)
BLOCKED_CLAIM = re.compile(r"\b(?:action|decision|request|recommendation|change|consolidation|modification|extension|it)\s+(?:is|are|remains|has\s+been)\s+(?:currently\s+)?blocked\b|\bcannot\s+proceed\b", re.IGNORECASE)
BLOCKED_WORDS = re.compile(r"\b(?:block\w*|cannot|can't|not\s+(?:permitted|eligible|allowed)|ineligible|no\s+accountable\s+owner|must\s+(?:first\s+)?(?:assign|resolve))\b", re.IGNORECASE)


def validate_final_decision(decision: DecisionResult, db: Session) -> DecisionResult:
    notes: List[str] = []
    asset_ids = {a for (a,) in db.query(AnalyticsAssets.asset_id).all()}
    model_ids = {m for (m,) in db.query(SemanticModels.model_id).all()}

    # 1-2. Every target must exist and be eligible for this action.
    if decision.decision in TARGETED and decision.target_asset_ids:
        kept: List[str] = []
        for target in decision.target_asset_ids:
            if target not in asset_ids:
                notes.append("Removed a target asset ID that is not in the analytics catalog.")
                continue
            check = check_target(db, target, decision.decision.value)
            if check.eligible:
                kept.append(target)
                continue
            notes.append(f"Removed ineligible target {target}: {' '.join(check.reasons)}")
            if all(t.get("asset_id") != target for t in decision.ineligible_targets):
                decision.ineligible_targets.append(check.as_dict())
            for reason in check.reasons:
                if reason not in decision.blockers:
                    decision.blockers.append(reason)
        if kept != decision.target_asset_ids:
            decision.target_asset_ids = kept
            if not kept:
                decision.target_model_ids = []
                decision.action_status = ActionStatus.BLOCKED
                rejected = ", ".join(t["asset_id"] for t in decision.ineligible_targets) or "the proposed target"
                decision.primary_recommendation = (
                    f"{decision.decision.value.replace('_', ' ').title()} is blocked: {rejected} cannot be an actionable target. "
                    "Resolve the governance blockers, or ask BIOS to re-evaluate eligible alternatives."
                )
                decision.next_steps = [
                    f"Assign and verify an accountable owner for {rejected}, or resolve its critical findings." ,
                    "Re-submit the request so BIOS re-evaluates eligible alternatives.",
                ] + [s for s in decision.next_steps if not any(t["asset_id"] in s for t in decision.ineligible_targets)]
    decision.target_model_ids = [m for m in decision.target_model_ids if m in model_ids]

    # 3. Blockers naming a target, or request-level blockers, block the action.
    if decision.decision in TARGETED | {DecisionType.BUILD_NEW} and decision.action_status != ActionStatus.BLOCKED:
        affecting = [b for b in decision.blockers if not ENTITY_ID.findall(b) or set(ENTITY_ID.findall(b)) & set(decision.target_asset_ids)]
        if affecting:
            decision.action_status = ActionStatus.BLOCKED
            notes.append("Action status set to BLOCKED: a governance blocker applies to the target or the whole request.")
        elif decision.decision in TARGETED and not decision.target_asset_ids and decision.ineligible_targets:
            decision.action_status = ActionStatus.BLOCKED
            notes.append("Action status set to BLOCKED: no eligible target remains.")

    # 4-5. Approval: consequential or blocked actions always need it; approval never clears a blocker.
    if decision.decision in CONSEQUENTIAL or decision.action_status == ActionStatus.BLOCKED:
        if decision.decision not in (DecisionType.NEEDS_CLARIFICATION, DecisionType.INFORMATIONAL) and not decision.human_approval_required:
            decision.human_approval_required = True
            notes.append("Human approval set to required for a consequential or blocked action.")
    if decision.action_status == ActionStatus.ACTIONABLE and decision.decision in CONSEQUENTIAL:
        decision.action_status = ActionStatus.REQUIRES_APPROVAL
        notes.append("A consequential action cannot be ACTIONABLE without approval.")

    # 6. Narrative consistency.
    narrative = decision.llm_narrative
    if narrative:
        rejected_ids = {t["asset_id"] for t in decision.ineligible_targets}
        cited = set(ENTITY_ID.findall(narrative))
        reason = None
        if cited - asset_ids - model_ids:
            reason = "it cites IDs that are not in the catalog"
        elif cited & rejected_ids and not BLOCKED_WORDS.search(narrative):
            reason = f"it presents {', '.join(sorted(cited & rejected_ids))} as usable although it is not an eligible target"
        elif cited - set(decision.target_asset_ids) and ACTION_VERBS.search(narrative) and not BLOCKED_WORDS.search(narrative):
            reason = "it directs an action at an asset that is not the validated target"
        elif any(not check_target(db, a, "CONSOLIDATE").eligible for a in cited & asset_ids) and not BLOCKED_WORDS.search(narrative):
            reason = "it names an asset governance forbids acting on without saying so"
        elif decision.action_status != ActionStatus.BLOCKED and BLOCKED_CLAIM.search(narrative):
            reason = "it says the action is blocked although governance permits it (blockers apply to other assets)"
        elif decision.action_status == ActionStatus.BLOCKED and not BLOCKED_WORDS.search(narrative):
            reason = "it does not say the action is blocked"
        elif decision.decision in TARGETED and decision.target_asset_ids and cited and not cited & (set(decision.target_asset_ids) | rejected_ids | set(ENTITY_ID.findall(decision.rationale))):
            reason = "it names assets that are not part of the decision"
        if reason:
            decision.llm_narrative = None
            notes.append(f"Discarded the AI-drafted narrative because {reason}.")

    decision.validation_notes = notes or ["Final decision passed deterministic validation unchanged."]
    return decision
