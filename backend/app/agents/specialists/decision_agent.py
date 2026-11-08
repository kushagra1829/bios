import json
import logging
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.agents.answering.eligibility import check_target
from backend.app.agents.entity_catalog import expand_market_scope
from backend.app.agents.schemas import (
    ActionStatus,
    BusinessIntent,
    RequestType,
    DiscoveredAsset,
    DiscoveryResult,
    KpiAnalysisResult,
    KpiMatch,
    DuplicationResult,
    GovernanceAgentResult,
    GeographyStatus,
    DecisionNarrative,
    DecisionResult,
    DecisionType,
    DecisionAlternative,
)
from backend.app.agents.specialists.llm_assisted import LLMAssistedAgent
from backend.app.models.core import AnalyticsAssets
from backend.app.models.domain import Products
from backend.app.models.governance import AssetKpiMap, GovernanceFindings, KpiCatalog, MigrationBacklog
from backend.app.models.lifecycle import LifecycleAssetAssessments, MigrationAssessments

logger = logging.getLogger(__name__)

_DUPLICATE_THRESHOLD = 0.65  # DuplicationAgent.DUPLICATE_THRESHOLD
_ENDORSEMENT_RANK = {"certified": 2, "promoted": 1}
_MAX_PRODUCT_OPTIONS = 5
_ENTITY_ID_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{2,}\b")
_MAX_NARRATIVE_ITEMS = 8
_MAX_NARRATIVE_ITEM_CHARS = 300


class DecisionAgent(LLMAssistedAgent):
    """
    Specialist Agent 6: Decision Synthesis.
    Synthesizes outputs from Intent, Discovery, KPI Intelligence, Duplication, and Governance.
    Adheres strictly to the Bayer governance hierarchy:
      1. REUSE certified assets first (RULE-001).
      2. CONSOLIDATE redundant/duplicate analytics.
      3. MODIFY existing semantic models and reports to add missing metrics.
      4. MIGRATE rationalised legacy Tableau assets.
      5. BUILD_NEW only as a last resort when reuse/modify are unviable.
      6. NEEDS_CLARIFICATION when intent is ambiguous or missing key specifications.
    Never overrides governance blockers. Always mandates human approval for consequential actions.

    The decision matrix is deterministic and runs first. The LLM only writes llm_narrative
    from the finished decision, so it cannot affect the decision, blockers or approvals.
    """

    agent_name = "DecisionAgent"

    def process(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        duplication: DuplicationResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> DecisionResult:
        types = intent.request_types or [RequestType.ASSET_REQUEST]
        if RequestType.ASSET_REQUEST in types:
            decision = self._decide(intent, discovery, kpi_analysis, duplication, governance, db)
        else:
            decision = self._answer_question(intent, discovery, governance, db)
        self._finalize_status(decision, intent)
        decision.active_finding_ids = list(governance.active_finding_ids)
        decision.out_of_scope_warnings = list(governance.out_of_scope_warnings)
        if governance.out_of_scope_finding_ids:
            decision.rationale += (
                f" {len(governance.out_of_scope_finding_ids)} governance finding(s) on assets outside the requested "
                "scope are reported separately and aren't blockers for this request."
            )
        decision.llm_narrative = self._narrate(decision)
        return decision

    # ------------------------------------------------------------------ question answers
    def _answer_question(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> DecisionResult:
        """
        Data, governance and migration questions get an answer, not an asset action. The answers
        were computed from source records by the Discovery step; this only states the outcome.
        An imperative lifecycle command naming an asset ("Retire AST-0268") is a real action and
        goes through target eligibility instead.
        """
        primary = intent.request_types[0]
        security = [a for a in intent.ambiguities if a.category == "security_override_attempt"]
        warnings = (
            ["SECURITY NOTICE: instructions to override governance were ignored. Standard governance rules apply."] if security else []
        )

        command = re.match(
            r"^\s*(?:please\s+)?(?:go\s+ahead\s+and\s+|now\s+)?(retire|decommission|sunset|archive|migrate|move)\b",
            intent.raw_prompt,
            re.IGNORECASE,
        )
        named = [a for a in intent.asset_ids_mentioned if a.startswith("AST-")]
        if primary == RequestType.MIGRATION_QUESTION and command and named:
            action = DecisionType.MIGRATE if command.group(1).lower() in ("migrate", "move") else DecisionType.RETIRE
            return self._lifecycle_command(action, named, governance, db, warnings)
        if primary == RequestType.MIGRATION_QUESTION and discovery.migration_answer is not None:
            answer = discovery.migration_answer
            unscoped = not named and not intent.products and not intent.markets
            singular = re.search(
                r"\b(?:report|dashboard|workbook|app|asset)\b(?!s)", intent.raw_prompt, re.IGNORECASE
            ) and not re.search(r"\b(?:which|what|list|all|any|every|how\s+many|show)\b", intent.raw_prompt, re.IGNORECASE)
            if (command and not named) or (unscoped and singular):
                # "Retire the abandoned report" names no asset: BIOS never picks one to act on.
                return DecisionResult(
                    decision=DecisionType.NEEDS_CLARIFICATION,
                    confidence=0.85,
                    primary_recommendation=(
                        "Which asset do you mean? BIOS won't choose an asset to migrate or retire on your behalf."
                    ),
                    rationale=(
                        f"The request asks for a lifecycle action on an unnamed asset. {answer.total_matching} migration-backlog "
                        "record(s) match the stated scope; each lifecycle action needs a named asset, its rationale (RULE-008) and approval."
                    ),
                    warnings=warnings,
                    human_approval_required=False,
                    next_steps=["Name the asset ID, or the product and market, so BIOS can show that asset's recommended path."],
                )
            if len(named) == 1 and answer.total_matching == 1:
                return self._backlog_path_decision(named[0], answer, governance, db, warnings)

        if primary in (RequestType.DATA_QUESTION, RequestType.BUSINESS_DATA_QUESTION) and discovery.data_answer is not None:
            answer = discovery.data_answer
            if answer.status == "NEEDS_CLARIFICATION":
                return DecisionResult(
                    decision=DecisionType.NEEDS_CLARIFICATION,
                    confidence=0.85,
                    primary_recommendation=answer.headline,
                    rationale=" ".join(answer.clarification) or answer.headline,
                    warnings=warnings,
                    human_approval_required=False,
                    next_steps=list(answer.clarification),
                )
            counts_summary = (
                ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in answer.coverage.value_type_counts.items())
                if answer.coverage and answer.coverage.value_type_counts
                else ""
            )
            rationale_parts = [
                f"Business data question answered directly from {answer.source.get('sheet', 'Product_Market_Monthly')} ({answer.status}).",
                f"Calculated result: {answer.headline}.",
            ]
            if counts_summary:
                rationale_parts.append(f"Synthetic data breakdown: {counts_summary}.")
            if answer.caveats:
                rationale_parts.append(f"Reporting bounds: {'; '.join(answer.caveats)}.")
            rationale_parts.append("No analytics asset action was requested, so none is recommended.")

            return DecisionResult(
                decision=DecisionType.INFORMATIONAL,
                confidence=1.0 if answer.status == "ANSWERED" else 0.9,
                primary_recommendation=answer.headline,
                rationale=" ".join(rationale_parts),
                warnings=warnings,
                human_approval_required=False,
                next_steps=list(answer.clarification) if answer.clarification else [],
            )

        if primary == RequestType.GOVERNANCE_QUESTION and discovery.governance_answer is not None:
            answer = discovery.governance_answer
            return DecisionResult(
                decision=DecisionType.INFORMATIONAL,
                confidence=1.0,
                primary_recommendation=answer.headline,
                rationale=(
                    "Governance question answered from the deterministic governance engine's findings and the catalog "
                    f"({answer.question_kind}, {answer.total_matching} matching record(s))."
                ),
                warnings=warnings,
                human_approval_required=False,
                next_steps=[v.required_action for v in answer.findings if v.kind == "BLOCKER" and v.required_action][:3],
            )

        if primary == RequestType.MIGRATION_QUESTION and discovery.migration_answer is not None:
            answer = discovery.migration_answer
            return DecisionResult(
                decision=DecisionType.INFORMATIONAL,
                confidence=1.0,
                primary_recommendation=answer.headline,
                rationale=(
                    "Migration question answered from Migration_Backlog with governance findings attached. Each path is a "
                    "recommendation; executing any of them is a consequential lifecycle action."
                ),
                warnings=warnings,
                human_approval_required=answer.total_matching > 0,
                next_steps=(
                    ["Raise an approval request for each asset you decide to migrate, consolidate or retire."]
                    if answer.total_matching
                    else []
                ),
            )

        return DecisionResult(
            decision=DecisionType.NEEDS_CLARIFICATION,
            confidence=0.5,
            primary_recommendation="BIOS couldn't find records that answer this question. Please add a product, market or asset ID.",
            rationale="No answer could be computed from the source records.",
            warnings=warnings,
            human_approval_required=False,
            next_steps=["Name a product, market, KPI or asset ID."],
        )

    def _backlog_path_decision(self, asset_id, answer, governance, db, warnings) -> DecisionResult:
        """A migration question about one asset: its Migration_Backlog path, checked against governance."""
        row = next(iter(answer.groups.values()))[0]
        path = row["recommended_path"]
        action = {
            "MIGRATE": DecisionType.MIGRATE,
            "CONSOLIDATE_BEFORE_MIGRATION": DecisionType.CONSOLIDATE,
            "REBUILD_ON_SHARED_MODEL": DecisionType.MODIFY,
            "RETIRE": DecisionType.RETIRE,
        }.get(path, DecisionType.NEEDS_CLARIFICATION)
        if action == DecisionType.NEEDS_CLARIFICATION:
            return DecisionResult(
                decision=action, confidence=0.8,
                primary_recommendation=f"{asset_id} needs human review before any migration path is chosen (Migration_Backlog: HUMAN_REVIEW).",
                rationale=f"Backlog reason: {row['reason']}.", warnings=warnings, human_approval_required=False,
                next_steps=["Ask the asset owner and BI governance to review the asset and choose a path."],
            )
        check = check_target(db, asset_id, action.value)
        blockers = list(check.reasons) + [b for b in row.get("governance_blockers", []) if b not in " ".join(check.reasons)]
        return DecisionResult(
            decision=action,
            confidence=0.85,
            primary_recommendation=(
                f"{row['path_label']} for {asset_id} ('{row['asset_name']}'), onto model {row['candidate_target_model_id']}"
                + (" — blocked until the governance blockers are resolved." if blockers else ", subject to approval.")
            ),
            rationale=(
                f"Migration_Backlog records path {path} for {asset_id} (status {row['status']}, complexity {row['complexity']}, "
                f"reason '{row['reason']}'). This is a synthetic scenario input, so it is a recommendation, not an approved decision."
            ),
            target_asset_ids=[asset_id] if not blockers else [],
            target_model_ids=[row["candidate_target_model_id"]] if row.get("candidate_target_model_id") and not blockers else [],
            blockers=blockers,
            warnings=warnings + list(check.warnings),
            human_approval_required=True,
            action_status=ActionStatus.BLOCKED if blockers else ActionStatus.REQUIRES_APPROVAL,
            ineligible_targets=[check.as_dict()] if not check.eligible else [],
            next_steps=[
                "Raise an approval request; the asset's accountable owner must approve the lifecycle action.",
                "Validate metric parity against the Tableau source before cut-over." if action == DecisionType.MIGRATE else
                "Document the rationale and downstream impact (RULE-008).",
            ],
        )

    def _lifecycle_command(self, action, asset_ids, governance, db, warnings) -> DecisionResult:
        checks = [check_target(db, asset_id, action.value) for asset_id in asset_ids]
        blockers: List[str] = []
        for check in checks:
            blockers.extend(check.reasons)
        # RULE-008 retirement protection is part of check_target(..., 'RETIRE').
        eligible = [c.asset_id for c in checks if c.eligible]
        verb = "Retiring" if action == DecisionType.RETIRE else "Migrating"
        steps = []
        if any("RULE-003" in b for b in blockers):
            steps.append("Assign and verify an accountable owner.")
        if any("RULE-008" in b for b in blockers):
            steps.append("Complete a retirement impact assessment and designate a successor report (RULE-008).")
        steps.append("Submit an approval request once any blockers are cleared.")
        return DecisionResult(
            decision=action,
            confidence=0.9,
            primary_recommendation=(
                f"{verb} {', '.join(asset_ids)} is blocked until the governance blockers are resolved."
                if blockers
                else f"{verb} {', '.join(asset_ids)} can be requested; it needs human approval before anything changes."
            ),
            rationale=(
                f"{verb} is a consequential lifecycle action. BIOS checked owner authority and critical findings"
                f"{' and RULE-008 retirement explainability' if action == DecisionType.RETIRE else ''} for {', '.join(asset_ids)}."
            ),
            target_asset_ids=eligible if not blockers else [],
            blockers=blockers,
            warnings=warnings,
            human_approval_required=True,
            action_status=ActionStatus.BLOCKED if blockers else ActionStatus.REQUIRES_APPROVAL,
            ineligible_targets=[c.as_dict() for c in checks if not c.eligible],
            next_steps=steps,
        )

    # ------------------------------------------------------------------ status and targets
    @staticmethod
    def _blocker_ids(text: str) -> List[str]:
        return re.findall(r"\b(?:AST|SM)-\d{3,4}\b", text)

    def _blockers_affecting(self, blockers: List[str], target_ids: List[str]) -> List[str]:
        """Blockers that stop acting on these targets: request-level ones, and ones naming a target."""
        affecting = []
        for b in blockers:
            ids = self._blocker_ids(b)
            if not ids or any(i in target_ids for i in ids):
                affecting.append(b)
        return affecting

    def _finalize_status(self, decision: DecisionResult, intent: BusinessIntent) -> None:
        decision.next_steps = [s for s in decision.next_steps if s]
        if decision.action_status == ActionStatus.BLOCKED:
            if decision.decision not in (DecisionType.NEEDS_CLARIFICATION, DecisionType.INFORMATIONAL):
                decision.human_approval_required = True
            return
        if decision.decision == DecisionType.NEEDS_CLARIFICATION:
            decision.action_status = ActionStatus.NEEDS_INPUT
            return
        if decision.decision == DecisionType.INFORMATIONAL:
            decision.action_status = (
                ActionStatus.REQUIRES_APPROVAL if decision.human_approval_required else ActionStatus.NOT_APPLICABLE
            )
            return
        affecting = self._blockers_affecting(decision.blockers, decision.target_asset_ids)
        if affecting or (decision.ineligible_targets and not decision.target_asset_ids):
            decision.action_status = ActionStatus.BLOCKED
            decision.human_approval_required = True
        elif decision.human_approval_required:
            decision.action_status = ActionStatus.REQUIRES_APPROVAL
        else:
            decision.action_status = ActionStatus.ACTIONABLE

    @staticmethod
    def _trust_rank(asset: DiscoveredAsset) -> tuple:
        return (
            -_ENDORSEMENT_RANK.get(asset.endorsement, 0),
            0 if asset.lifecycle_status == "active" else 1,
            -asset.estimated_audience,
            asset.asset_id,
        )

    def _policy_unowned_request(self, intent: BusinessIntent, governance: GovernanceAgentResult) -> Optional[DecisionResult]:
        """'Build a dashboard using an asset with no accountable owner' - a request RULE-003 forbids outright."""
        if intent.asset_ids_mentioned:
            return None
        if not re.search(
            r"\b(?:no\s+|without\s+(?:an?\s+|the\s+)?|missing\s+(?:an?\s+)?)(?:accountable\s+|assigned\s+|active\s+)?owners?\b|\bunowned\b|\bownerless\b",
            intent.raw_prompt,
            re.IGNORECASE,
        ):
            return None
        return DecisionResult(
            decision=DecisionType.MODIFY,
            confidence=0.9,
            primary_recommendation=(
                "Building on, extending or reusing an asset that has no accountable owner is not permitted. "
                "Assign an owner first, or let BIOS find an owned, trusted asset instead."
            ),
            rationale=(
                "RULE-003 (Owner required): an asset without an accountable owner cannot be safely extended, modified or used as "
                "a consolidation target, and nobody holds the authority to approve the change (owner authority, N4). "
                "BIOS therefore blocks the request rather than proposing a workaround."
            ),
            blockers=[
                "RULE-003 BLOCKER: The request asks to build on an asset with no accountable owner. Unowned assets cannot be extended."
            ]
            + list(governance.blockers),
            warnings=list(governance.warnings),
            human_approval_required=True,
            action_status=ActionStatus.BLOCKED,
            next_steps=[
                "Safe alternative 1: raise an ownership assignment for the asset; BIOS re-evaluates once the owner is verified.",
                "Safe alternative 2: name the product and market so BIOS can find an owned, endorsed asset to reuse or extend.",
            ],
        )

    def _asset_directed(self, intent, discovery, governance, db, kpi_analysis=None) -> Optional[DecisionResult]:
        """A request to act on a named asset ("Add forecast variance to AST-0268")."""
        named = [a for a in intent.asset_ids_mentioned if a.startswith("AST-")]
        if not named:
            return None
        text = intent.raw_prompt
        if re.search(r"\b(?:consolidat\w*|merge|combine)\b", text, re.IGNORECASE):
            action = DecisionType.CONSOLIDATE
        elif re.search(r"\b(?:retire|decommission|sunset|archive)\b", text, re.IGNORECASE):
            action = DecisionType.RETIRE
        elif re.search(r"\bmigrat\w*\b", text, re.IGNORECASE):
            action = DecisionType.MIGRATE
        elif re.search(r"\b(?:modify|extend|enhance|update|add|change|edit|publish|promote|include|approve)\b", text, re.IGNORECASE):
            action = DecisionType.MODIFY
        elif re.search(r"\b(?:reuse|re-use|use|access|open|view)\b", text, re.IGNORECASE):
            action = DecisionType.REUSE
        else:
            action = DecisionType.MODIFY
        # Reuse of a named asset needs evidence that it carries the requested KPIs. Without it the
        # asset can't answer the request as it stands, so the honest action is to extend it.
        kpi_gap_note = ""
        requested = set(kpi_analysis.canonical_approved_kpi_ids) if kpi_analysis else set()
        if action == DecisionType.REUSE and requested:
            mapped = {row.kpi_id for asset_id in named for row in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset_id).all()}
            if not mapped & requested:
                action = DecisionType.MODIFY
                kpi_gap_note = (
                    f" Asset_KPI_Map shows {', '.join(named)} doesn't carry the requested KPI(s) {', '.join(sorted(requested))}, "
                    "so it can't be reused as-is; it would have to be extended."
                )
        checks = [check_target(db, asset_id, action.value) for asset_id in named]
        unknown = [c.asset_id for c in checks if not c.exists]
        if unknown:
            # Never act on, or invent facts about, an asset the catalog doesn't contain.
            return DecisionResult(
                decision=DecisionType.NEEDS_CLARIFICATION,
                confidence=0.9,
                # The unknown ID is deliberately not repeated: BIOS never cites an ID the catalog doesn't hold.
                primary_recommendation=(
                    f"The asset ID{'s' if len(unknown) > 1 else ''} named in the request {'are' if len(unknown) > 1 else 'is'} "
                    "not in the analytics catalog, so BIOS can't act on it."
                ),
                rationale=f"BIOS checked all {discovery.total_searched} analytics assets in the catalog and found no asset with that ID.",
                blockers=list(governance.blockers),
                warnings=list(governance.warnings),
                human_approval_required=False,
                next_steps=["Check the asset ID, or describe the product, market and KPIs so BIOS can find the right asset."],
            )
        eligible = [c for c in checks if c.eligible]
        ineligible = [c for c in checks if not c.eligible]
        request_level = [b for b in governance.blockers if not self._blocker_ids(b)]
        asset_by_id = {a.asset_id: a for a in discovery.exact_matches + discovery.partial_matches}
        model_ids = [
            asset_by_id[c.asset_id].model_id
            for c in eligible
            if c.asset_id in asset_by_id and asset_by_id[c.asset_id].model_id
        ]
        verb = {"MODIFY": "Modifying", "REUSE": "Reusing", "CONSOLIDATE": "Consolidating", "RETIRE": "Retiring", "MIGRATE": "Migrating"}[
            action.value
        ]
        blocked = bool(ineligible) or bool(request_level)
        reasons = " ".join(r for c in ineligible for r in c.reasons)
        existing = " ".join(governance.blockers)
        steps: List[str] = []
        unowned = [c.asset_id for c in ineligible if "RULE-003" in c.rule_ids]
        if unowned:
            steps.append(f"Assign and verify an accountable owner for {', '.join(unowned)}; then ask BIOS to re-evaluate.")
        steps.extend(f"Resolve: {r}" for c in ineligible for r in c.reasons if "RULE-003" not in r)
        if request_level:
            steps.append("Resolve the request-level governance blockers listed below.")
        if not blocked and action != DecisionType.REUSE:
            steps.append("Submit the change for approval by the asset's accountable owner.")
        return DecisionResult(
            decision=action,
            confidence=0.88,
            primary_recommendation=(
                f"{verb} {', '.join(c.asset_id for c in ineligible) or ', '.join(named)} is blocked. {reasons}".strip()
                if blocked
                else f"{verb} {', '.join(named)} is permitted, subject to "
                f"{'human approval' if action != DecisionType.REUSE else 'access provisioning'}."
            ),
            rationale=(
                f"The request names {', '.join(named)}. BIOS checked owner authority and active critical findings before "
                f"allowing the action.{kpi_gap_note} {reasons}".strip()
                + (f" Request-level blockers: {'; '.join(request_level)}" if request_level else "")
            ),
            target_asset_ids=[c.asset_id for c in eligible] if not blocked else [],
            target_model_ids=model_ids if not blocked else [],
            blockers=list(governance.blockers) + [r for c in ineligible for r in c.reasons if r not in existing],
            warnings=list(governance.warnings) + [w for c in checks for w in c.warnings],
            human_approval_required=action != DecisionType.REUSE or blocked,
            action_status=(
                ActionStatus.BLOCKED
                if blocked
                else (ActionStatus.ACTIONABLE if action == DecisionType.REUSE else ActionStatus.REQUIRES_APPROVAL)
            ),
            ineligible_targets=[c.as_dict() for c in ineligible],
            next_steps=steps[:5],
        )

    def _duplication_assessment(self, intent, discovery, duplication, governance, db) -> Optional[DecisionResult]:
        """Gate-backed consolidation when existing in-scope assets genuinely overlap (G1-G4 pass)."""
        pairs = duplication.consolidation_eligible_pairs
        if not pairs and not intent.duplication_question:
            return None
        if not pairs:
            groups = duplication.title_alike_groups
            described = "; ".join(f"'{g['title_root']}' ({', '.join(g['asset_ids'])}): {g['verdict']}" for g in groups[:5])
            return DecisionResult(
                decision=DecisionType.NEEDS_CLARIFICATION,
                confidence=0.8,
                primary_recommendation=(
                    "Don't consolidate yet: none of the similar-looking assets BIOS found is a proven duplicate. "
                    "Tell BIOS which assets you mean for a pair-specific assessment."
                ),
                rationale=(
                    f"BIOS ran the staged G1-G4 duplication gates over {', '.join(intent.products) or 'the'} assets"
                    f"{' in ' + ', '.join(intent.markets) if intent.markets else ''}: no pair passed. "
                    f"Same-title groups checked: {described or 'none'}. Title similarity alone never justifies consolidation."
                ),
                blockers=list(governance.blockers),
                warnings=list(governance.warnings),
                human_approval_required=False,
                next_steps=[
                    "Name the assets (asset IDs) you consider similar.",
                    "BIOS will compare their product, market, KPI and semantic-model evidence pair by pair through the G1-G4 gates.",
                ],
            )
        asset_ids = list(dict.fromkeys(a for pair in pairs for a in pair))
        known = {a.asset_id: a for a in discovery.exact_matches + discovery.partial_matches}
        ordered = sorted([known[a] for a in asset_ids if a in known], key=self._trust_rank)
        if not ordered:
            return None
        rejected = []
        target = None
        for asset in ordered:
            check = check_target(db, asset.asset_id, "CONSOLIDATE")
            if check.eligible:
                target = asset
                break
            rejected.append(check.as_dict())
        gate = next((g for g in duplication.gate_evaluations if g["consolidation_eligible"]), None)
        gate_text = (
            f"Gates: G1 scope pass; G2 canonical-concept overlap {gate['g2_canonical_group_jaccard']:.2f}; "
            f"G3 exact-KPI overlap {gate['g3_exact_kpi_jaccard']:.2f}; G4 shared model/workspace {'yes' if gate['g4_shares_model'] else 'no'}."
            if gate
            else ""
        )
        if target is None:
            return DecisionResult(
                decision=DecisionType.CONSOLIDATE,
                confidence=0.8,
                primary_recommendation=f"Consolidating {', '.join(asset_ids)} is warranted but blocked: no candidate target passes governance.",
                rationale=f"The duplication gates confirm overlap between {', '.join(' and '.join(p) for p in pairs)}. {gate_text}",
                blockers=list(governance.blockers) + [r for item in rejected for r in item["reasons"]],
                warnings=list(governance.warnings),
                human_approval_required=True,
                action_status=ActionStatus.BLOCKED,
                ineligible_targets=rejected,
                next_steps=["Assign an accountable owner to one of the overlapping assets, then re-evaluate."],
            )
        sources = [a for a in asset_ids if a != target.asset_id]
        return DecisionResult(
            decision=DecisionType.CONSOLIDATE,
            confidence=0.86,
            primary_recommendation=(
                f"Consolidate {', '.join(sources)} into {target.asset_id} ('{target.asset_name}') instead of building another asset."
            ),
            rationale=(
                f"{len(asset_ids)} existing {target.product_scope} assets in {target.market_scope} overlap: the staged duplication "
                f"gates confirm {', '.join(' + '.join(p) for p in pairs)} share scope and governed KPI concepts. {gate_text} "
                f"{target.asset_id} is the strongest target ({target.endorsement} endorsement, lifecycle '{target.lifecycle_status}', "
                f"owner {target.owner_name}, audience {target.estimated_audience:,})."
            ),
            target_asset_ids=[target.asset_id],
            target_model_ids=[target.model_id] if target.model_id else [],
            alternatives=[
                DecisionAlternative(
                    action="REUSE",
                    target_id=target.asset_id,
                    pros="Immediate access to the strongest asset.",
                    cons="Leaves the overlapping asset(s) in place, so the duplication remains.",
                ),
                DecisionAlternative(
                    action="BUILD_NEW",
                    target_id=None,
                    pros="None for this scope.",
                    cons="Adds another overlapping asset; violates RULE-001.",
                ),
            ],
            blockers=list(governance.blockers),
            warnings=list(governance.warnings),
            human_approval_required=True,
            ineligible_targets=rejected,
            next_steps=[
                f"Raise a CONSOLIDATE approval request for {', '.join(sources)} into {target.asset_id}; "
                f"the accountable owner ({target.owner_name}) must approve.",
                "Confirm metric parity for the shared KPIs before redirecting users.",
                "Retire the consolidated source asset(s) only after a RULE-008 impact assessment.",
            ],
        )


    @staticmethod
    def _rank_modify_pool(pool: List[DiscoveredAsset], kpi_analysis: KpiAnalysisResult, db: Session) -> List[DiscoveredAsset]:
        """
        Extend the asset with the most evidence for the request: requested KPIs it already maps,
        then KPIs of the same family (Net Sales Growth for Net Sales), then active lifecycle and trust.
        Discovery order breaks ties, so an asset the request names stays first.
        """
        requested = set(kpi_analysis.canonical_approved_kpi_ids)
        if not requested:
            return list(pool)
        names = [m.matched_kpi_name.lower() for m in kpi_analysis.matches if m.matched_kpi_name and m.matched_kpi_id in requested]

        def key(item):
            index, asset = item
            if asset.evidence.get("named_in_request"):
                return (-1, 0, 0, 0, index)
            rows = (
                db.query(AssetKpiMap.kpi_id, KpiCatalog.kpi_name)
                .join(KpiCatalog, KpiCatalog.kpi_id == AssetKpiMap.kpi_id)
                .filter(AssetKpiMap.asset_id == asset.asset_id)
                .all()
            )
            exact = sum(1 for kpi_id, _ in rows if kpi_id in requested)
            family = sum(1 for _, name in rows if any(name.lower().startswith(n) for n in names))
            return (-exact, -family, 0 if asset.lifecycle_status == "active" else 1, -_ENDORSEMENT_RANK.get(asset.endorsement, 0), index)

        return [asset for _, asset in sorted(enumerate(pool), key=key)]

    @staticmethod
    def _clarification_headline(intent: BusinessIntent, discovery: DiscoveryResult) -> str:
        if intent.products and (discovery.exact_matches or discovery.partial_matches):
            existing = discovery.exact_matches + discovery.partial_matches
            trusted = [a for a in existing if a.endorsement in ("certified", "promoted") and a.lifecycle_status == "active"]
            return (
                f"Before anything new is built: BIOS already found {len(existing)} existing {', '.join(intent.products)} "
                f"asset(s){f', {len(trusted)} of them endorsed and active' if trusted else ''}. Tell BIOS the missing details "
                "below so it can check whether one already serves the need."
            )
        return "Clarification required before analytics provisioning can proceed."

    def _reuse_candidate(self, intent, discovery, kpi_analysis, governance, db):
        """
        The best trusted exact match that governance permits reusing, with KPI evidence when KPIs were
        requested. Returns (asset or None, rejected targets, warnings).
        """
        requested = set(kpi_analysis.canonical_approved_kpi_ids)
        rejected: List[Dict[str, Any]] = []
        candidates = [a for a in discovery.exact_matches if a.endorsement in ("certified", "promoted")]
        discovery_request = re.search(
            r"\b(?:find|locate|search|is\s+there|are\s+there|do\s+we\s+have|existing|which\s+(?:dashboard|report|asset))\b",
            intent.raw_prompt, re.IGNORECASE,
        )
        if not candidates and intent.title_topics and not intent.markets and discovery_request:
            # "Find the certified Nubeqa Budget Management dashboard": product + title topic, any market.
            candidates = [a for a in discovery.exact_matches + discovery.partial_matches
                          if a.endorsement in ("certified", "promoted") and a.evidence.get("title_topic_match")]
            if re.search(r"\bcertified\b", intent.raw_prompt, re.IGNORECASE):
                candidates.sort(key=lambda a: 0 if a.endorsement == "certified" else 1)
        for asset in candidates:
            if self._blockers_affecting(governance.blockers, [asset.asset_id]):
                continue
            check = check_target(db, asset.asset_id, "REUSE")
            if not check.eligible:
                rejected.append(check.as_dict())
                continue
            if requested:
                mapped = {row.kpi_id for row in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset.asset_id).all()}
                if not mapped & requested and not asset.evidence.get("title_topic_match"):
                    continue
            return asset, rejected, check.warnings
        return None, rejected, []

    @staticmethod
    def _reuse_first_steps(intent: BusinessIntent, discovery: DiscoveryResult) -> List[str]:
        """A clarification on an asset request still shows what already exists: reuse comes before build."""
        if not intent.products:
            return []
        trusted = [
            a for a in discovery.exact_matches + discovery.partial_matches
            if a.endorsement in ("certified", "promoted") and a.lifecycle_status == "active" and a.owner_name
        ][:4]
        if not trusted:
            return []
        listing = "; ".join(f"{a.asset_id} '{a.asset_name}' ({a.market_scope}, {a.endorsement})" for a in trusted)
        return [f"Before anything new is built, check these existing trusted {', '.join(intent.products)} assets: {listing}."]

    @staticmethod
    def _clarification_steps(intent: BusinessIntent, geography_unresolved: bool) -> List[str]:
        """Ask only for what is actually missing, and say what is already settled."""
        steps: List[str] = []
        if geography_unresolved:
            geography = intent.geography
            step = f"Confirm the geographic scope for: {', '.join(geography.unresolved_geography)}."
            if geography.resolved_market_ids:
                step += f" Already resolved: {', '.join(geography.resolved_market_ids)}."
            suggested = [m for p in geography.phrases for m in p.suggested_market_ids]
            if suggested:
                step += f" Suggestions to confirm, not verified matches: {', '.join(dict.fromkeys(suggested))}."
            steps.append(step)
        elif not intent.markets:
            steps.append("Specify target country or regional market context.")
        for ambiguity in intent.ambiguities:
            if ambiguity.category == "term":
                steps.append(f"Confirm whether '{ambiguity.term}' refers to market {', '.join(ambiguity.candidates)}.")
        if not intent.products:
            steps.append("Specify target pharmaceutical brand/product.")
        if not intent.kpis:
            steps.append("Clarify required metric calculations.")
        if not intent.time_periods:
            steps.append("Specify the time frequency.")
        return steps or ["Resolve the items listed in the rationale."]

    def _decide_without_product(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> Optional[DecisionResult]:
        """
        Target an asset only if it's portfolio-wide (no product assumed), active, owned, on a
        semantic model, and has KPI or title evidence for a requested metric. Otherwise ask which
        product is meant. Returns None when nothing matched and a market was given, because
        that's a genuine gap for the normal decision path to assess.
        """
        candidates = discovery.exact_matches + discovery.partial_matches
        if not candidates and intent.markets:
            return None

        catalog_products = {name for (name,) in db.query(Products.product_name).all()}
        metrics = [m for m in kpi_analysis.matches if m.matched_kpi_id]
        ranked = []
        for asset in candidates:
            if asset.product_scope in catalog_products or asset.lifecycle_status != "active":
                continue
            if not asset.owner_name or not asset.model_id:
                continue
            mapped_ids = {row.kpi_id for row in db.query(AssetKpiMap).filter(AssetKpiMap.asset_id == asset.asset_id).all()}
            mapped = [m for m in metrics if m.matched_kpi_id in mapped_ids]
            title_only = [m for m in metrics if m not in mapped and _title_mentions(asset.asset_name, m)]
            if mapped or title_only:
                endorsement = _ENDORSEMENT_RANK.get(asset.endorsement, 0)
                ranked.append((-len(mapped), -len(title_only), -endorsement, -asset.match_score, asset.asset_id, asset, mapped, title_only))

        if not ranked:
            return self._ask_for_product(intent, candidates, governance)

        *_, asset, mapped, title_only = min(ranked, key=lambda item: item[:5])
        evidence = []
        if mapped:
            evidence.append(f"asset_kpi_map confirms {_metric_names(mapped)}")
        if title_only:
            evidence.append(f"only its title suggests {_metric_names(title_only)}, which asset_kpi_map doesn't confirm")
        scope_note = ""
        if intent.markets and asset.market_scope not in intent.markets:
            scope_note = f" It's scoped to {asset.market_scope}, within the requested {', '.join(intent.markets)}."

        next_steps = [
            "Confirm a portfolio-wide view meets the need, or name a product for a product-specific asset.",
            f"Submit a change request to {asset.owner_name}, owner of {asset.asset_id}.",
        ]
        if title_only:
            next_steps.insert(1, f"Verify that {asset.asset_id} calculates {_metric_names(title_only)}, then map the KPI.")

        return DecisionResult(
            decision=DecisionType.MODIFY,
            confidence=0.75 if not title_only else 0.6,
            primary_recommendation=f"Extend portfolio-wide asset {asset.asset_id} ('{asset.asset_name}'), subject to the limitations in the rationale.",
            rationale=(
                f"The request names no product, so BIOS looked for a portfolio-wide asset rather than assuming one. "
                f"{asset.asset_id} ('{asset.asset_name}') has scope '{asset.product_scope}', is active and has an owner. "
                f"Evidence: {'; '.join(evidence)}.{scope_note}"
            ),
            target_asset_ids=[asset.asset_id],
            target_model_ids=[asset.model_id],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=True,
            next_steps=next_steps,
        )

    def _ask_for_product(
        self,
        intent: BusinessIntent,
        candidates: List[DiscoveredAsset],
        governance: GovernanceAgentResult,
    ) -> DecisionResult:
        options = [f"{a.asset_id} '{a.asset_name}' ({a.product_scope})" for a in candidates[:_MAX_PRODUCT_OPTIONS]]
        if options:
            found = (
                f"Assets matching the request's market and title words are product-specific or lack supporting "
                f"evidence, so choosing one would assume a product: {'; '.join(options)}."
            )
        else:
            found = "With no product or market named, there's no scope to search on."
        steps = self._clarification_steps(intent, False)
        if options:
            steps.append(f"Assets that may apply once a product is named: {'; '.join(options)}.")
        return DecisionResult(
            decision=DecisionType.NEEDS_CLARIFICATION,
            confidence=0.85,
            primary_recommendation="Specify the product before BIOS recommends a target asset.",
            rationale=f"The request names no product. {found}",
            target_asset_ids=[],
            target_model_ids=[],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=False,
            next_steps=steps,
        )

    def _narrate(self, decision: DecisionResult) -> Optional[str]:
        """Draft a plain-language summary, rejecting any that contradicts the decision or cites unknown IDs."""
        facts = {
            "decision": decision.decision.value,
            "confidence": decision.confidence,
            "primary_recommendation": decision.primary_recommendation,
            "rationale": decision.rationale,
            "target_asset_ids": decision.target_asset_ids,
            "target_model_ids": decision.target_model_ids,
            "human_approval_required": decision.human_approval_required,
            "action_status": decision.action_status.value,
            "ineligible_target_ids": [t["asset_id"] for t in decision.ineligible_targets],
            "blocker_count": len(decision.blockers),
            "blockers": _bounded(decision.blockers),
            "warning_count": len(decision.warnings),
            "warnings": _bounded(decision.warnings),
            "next_steps": _bounded(decision.next_steps),
        }
        known_ids = set(_ENTITY_ID_PATTERN.findall(json.dumps(facts)))

        def guard(narrative: DecisionNarrative) -> None:
            if narrative.decision_echo != decision.decision:
                raise ValueError(f"narrative contradicts decision {decision.decision.value}")
            if narrative.human_approval_required_echo != decision.human_approval_required:
                raise ValueError("narrative contradicts the human approval requirement")
            if narrative.blocker_count_echo != len(decision.blockers):
                raise ValueError("narrative contradicts the governance blocker count")
            unknown = set(_ENTITY_ID_PATTERN.findall(narrative.summary)) - known_ids
            if unknown:
                raise ValueError(f"narrative cites IDs absent from the decision: {sorted(unknown)}")
            # Governance consistency: a rejected target may only be named as blocked, and a blocked
            # action may not be described as able to proceed.
            blocked_words = re.compile(r"\b(?:block\w*|cannot|can't|not\s+eligible|ineligible|no\s+accountable\s+owner)\b", re.IGNORECASE)
            rejected = {t["asset_id"] for t in decision.ineligible_targets}
            if rejected & set(_ENTITY_ID_PATTERN.findall(narrative.summary)) and not blocked_words.search(narrative.summary):
                raise ValueError("narrative presents an ineligible asset as a usable target")
            if decision.action_status == ActionStatus.BLOCKED and not blocked_words.search(narrative.summary):
                raise ValueError("narrative omits that the action is blocked")
            if decision.action_status != ActionStatus.BLOCKED and re.search(r"\b(?:action|decision|request|recommendation|change|consolidation|modification|extension|it)\s+(?:is|are|remains|has\s+been)\s+(?:currently\s+)?blocked\b|\bcannot\s+proceed\b", narrative.summary, re.IGNORECASE):
                raise ValueError("narrative claims the action is blocked although it is not")
            action_words = re.compile(r"\b(?:consolidat\w*|reus\w*|extend\w*|modif\w*|migrat\w*|retir\w*|merge)\b", re.IGNORECASE)
            others = set(_ENTITY_ID_PATTERN.findall(narrative.summary)) - set(decision.target_asset_ids) - set(decision.target_model_ids)
            if others and action_words.search(narrative.summary) and not blocked_words.search(narrative.summary):
                raise ValueError("narrative directs an action at an asset that is not the decision's target")

        narrative = self._llm_step(
            prompt=(
                "Explain this decision to a business stakeholder in at most three sentences. "
                "The decision is final: do not change, soften or question it. Use only the supplied "
                "facts, and cite only IDs that appear in them. State any blockers and any required "
                "human approval. If action_status is BLOCKED, say the action is blocked; otherwise never say the action is "
                "blocked (blockers on other assets don't block it). Never present an asset in "
                "ineligible_target_ids as a target; name it only as blocked. "
                "Copy decision, human_approval_required and blocker_count into the echo fields."
            ),
            schema=DecisionNarrative,
            system_prompt="You are the BIOS Decision Agent's communications assistant. You explain decisions; you do not make them.",
            context=facts,
            guard=guard,
        )
        return narrative.summary.strip() if narrative else None

    def _decide(
        self,
        intent: BusinessIntent,
        discovery: DiscoveryResult,
        kpi_analysis: KpiAnalysisResult,
        duplication: DuplicationResult,
        governance: GovernanceAgentResult,
        db: Session,
    ) -> DecisionResult:
        logger.info(f"[{self.agent_name}] Synthesizing multi-agent inputs into strategic recommendation")

        # 1. Check for Ambiguous / Missing Requirements
        # Geography the user stated but BIOS can't fully resolve could change the candidate assets,
        # so it gets no definitive action. A request that names no geography isn't affected.
        geography_unresolved = bool(intent.geography) and intent.geography.status in (
            GeographyStatus.NEEDS_CLARIFICATION,
            GeographyStatus.PARTIALLY_RESOLVED,
        )
        # A word that may or may not be a market could change the candidates too. It's a separate
        # question from geography, so it doesn't affect the geography status.
        unclear_term = any(a.category == "term" for a in intent.ambiguities)

        # Requests that governance decides before anything else.
        policy = self._policy_unowned_request(intent, governance)
        if policy is not None:
            return policy
        if not geography_unresolved:
            directed = self._asset_directed(intent, discovery, governance, db, kpi_analysis)
            if directed is not None:
                return directed

        # A named title topic ("Budget Mgmt") or a question about existing duplicates is specific
        # enough to search on without a KPI or time horizon; product and geography still count.
        relaxed = bool(intent.products) and (bool(discovery.title_topic_matches) or intent.duplication_question)
        gaps_that_count = [
            g for g in intent.missing_or_ambiguous
            if not relaxed or not g.startswith(("Specific metric", "Time horizon", "Target geographic market"))
        ]
        too_vague = (intent.confidence < 0.45 and not relaxed) or len(gaps_that_count) >= 3
        if too_vague or geography_unresolved or unclear_term:
            gaps = "; ".join(item.rstrip(".") for item in intent.missing_or_ambiguous)
            return DecisionResult(
                decision=DecisionType.NEEDS_CLARIFICATION,
                confidence=0.85,
                primary_recommendation=(
                    "Clarification required before analytics provisioning can proceed."
                    if geography_unresolved else self._clarification_headline(intent, discovery)
                ),
                rationale=(
                    "The business request lacks critical operational details required to evaluate "
                    f"existing assets: {gaps}. In accordance with "
                    "governance standards, analytics should not be commissioned without clear product scope, "
                    "geographic market, and metric definitions."
                ),
                target_asset_ids=[],
                target_model_ids=[],
                alternatives=[],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=False,
                next_steps=self._clarification_steps(intent, geography_unresolved)
                + ([] if geography_unresolved or unclear_term else self._reuse_first_steps(intent, discovery)),
            )

        # A request that names no product can't be pointed at one product's asset.
        if not intent.products:
            without_product = self._decide_without_product(intent, discovery, kpi_analysis, governance, db)
            if without_product is not None:
                return without_product

        # 2. Check for Governance Blockers
        has_critical_blockers = len(governance.blockers) > 0
        security_override_detected = any(a.category == "security_override_attempt" for a in intent.ambiguities)
        security_note = (
            " [SECURITY NOTICE: Unapproved prompt instructions attempting to override governance, bypass rules, "
            "or force greenfield builds were discarded. System adheres strictly to corporate governance.]"
            if security_override_detected
            else ""
        )

        # Check for matching migration backlog candidates in case MIGRATE applies
        migration_candidates = []
        if intent.products:
            prod = intent.products[0]
            migration_candidates = (
                db.query(MigrationBacklog)
                .filter(MigrationBacklog.product_scope.ilike(f"%{prod}%"))
                .all()
            )

        # 3. Decision Matrix Evaluation

        # Query lifecycle and migration intelligence if available
        def _get_lifecycle_note(asset_id: str) -> str:
            asm = (
                db.query(LifecycleAssetAssessments)
                .filter(LifecycleAssetAssessments.asset_id == asset_id)
                .order_by(LifecycleAssetAssessments.assessed_at.desc())
                .first()
            )
            if asm:
                return f" [Lifecycle Engine: {asm.recommended_action}, health score: {asm.composite_score:.1f}]"
            return ""

        # Option A: REUSE Existing Certified Asset - trusted, eligible and with KPI evidence.
        top_exact_certified, reuse_rejected, reuse_warnings = self._reuse_candidate(intent, discovery, kpi_analysis, governance, db)

        # Option 0: existing in-scope assets that the staged G1-G4 gates prove overlapping. A question
        # about duplicates is always answered by the gates; a build request is, when nothing is reusable.
        assessment = self._duplication_assessment(intent, discovery, duplication, governance, db)
        if assessment is not None and (intent.duplication_question or top_exact_certified is None):
            return assessment

        if top_exact_certified is not None:
            matched_kpi_cnt = len(kpi_analysis.canonical_approved_kpi_ids)
            lc_note = _get_lifecycle_note(top_exact_certified.asset_id)
            endorsement_title = "certified" if top_exact_certified.endorsement == "certified" else "promoted"
            rationale = (
                f"Existing {endorsement_title} asset {top_exact_certified.asset_id} ('{top_exact_certified.asset_name}') "
                f"already covers {top_exact_certified.product_scope} in {top_exact_certified.market_scope} "
                f"(endorsement: '{top_exact_certified.endorsement}', lifecycle: '{top_exact_certified.lifecycle_status}'). "
                f"It supports {matched_kpi_cnt} of the requested canonical KPIs{lc_note}. "
                f"In accordance with RULE-001 (Reuse before build), business users must be directed to this "
                f"{endorsement_title} report rather than creating redundant analytics.{security_note}"
            )

            alternatives = [
                DecisionAlternative(
                    action="MODIFY",
                    target_id=top_exact_certified.asset_id,
                    pros=f"Enhances an existing {endorsement_title} asset without creating new content.",
                    cons="Requires minor report change management and testing.",
                ),
                DecisionAlternative(
                    action="BUILD_NEW",
                    target_id=None,
                    pros="Complete customization for specific country request.",
                    cons="Violates RULE-001, increases BI estate sprawl and maintenance overhead.",
                ),
            ]

            override_blockers = [
                "SECURITY BLOCKER: Adversarial override attempt detected in prompt. Corporate governance rules cannot be bypassed."
            ] if security_override_detected else []

            not_active = top_exact_certified.lifecycle_status != "active"
            if duplication.consolidation_eligible_pairs:
                reuse_warnings = reuse_warnings + [
                    "Separately, the duplication gates (G1-G4) show existing overlap that should be rationalised: "
                    + "; ".join(" + ".join(p) for p in duplication.consolidation_eligible_pairs) + "."
                ]
            return DecisionResult(
                decision=DecisionType.REUSE,
                ineligible_targets=reuse_rejected,
                confidence=0.40 if security_override_detected else 0.92,
                primary_recommendation=f"Reuse existing {endorsement_title} report {top_exact_certified.asset_id} ('{top_exact_certified.asset_name}').",
                rationale=rationale,
                target_asset_ids=[top_exact_certified.asset_id],
                target_model_ids=[top_exact_certified.model_id] if top_exact_certified.model_id else [],
                alternatives=alternatives,
                blockers=governance.blockers + override_blockers,
                warnings=governance.warnings + reuse_warnings,
                # Reuse is read access, not a consequential change: no approval, but a non-active asset's
                # owner is asked to confirm availability (next step and warning below).
                human_approval_required=True if security_override_detected else False,
                next_steps=(
                    [f"Confirm with {top_exact_certified.owner_name or 'the owner'} that {top_exact_certified.asset_id} "
                     f"(lifecycle '{top_exact_certified.lifecycle_status}') will stay available."] if not_active else []
                ) + [
                    f"Provide user access to workspace containing {top_exact_certified.asset_id}.",
                    "Verify user filters cover the desired country-level granularity.",
                ],
            )

        # Option B: CONSOLIDATE Duplicate Assets
        consolidation_rejected: List[Dict[str, Any]] = []
        dup_asset_id = None
        if duplication.has_duplicates and duplication.primary_duplicate_asset_id:
            # The highest-similarity duplicate is the target only if governance permits acting on it.
            ranked = [c for c in duplication.candidates
                      if c.similarity_score >= _DUPLICATE_THRESHOLD and c.evidence.get("scope_compatible", True)]
            for cand in ranked:
                check = check_target(db, cand.asset_id, "CONSOLIDATE")
                if check.eligible:
                    dup_asset_id = cand.asset_id
                    break
                consolidation_rejected.append(check.as_dict())
        if dup_asset_id:
            lc_note = _get_lifecycle_note(dup_asset_id)
            dup_candidate = next(c for c in duplication.candidates if c.asset_id == dup_asset_id)
            rejected_note = (
                f" {', '.join(r['asset_id'] for r in consolidation_rejected)} scored higher but can't be a target: "
                + " ".join(reason for r in consolidation_rejected for reason in r["reasons"])
                if consolidation_rejected else ""
            )
            rationale = (
                f"High-confidence overlap detected (similarity {dup_candidate.similarity_score:.2f}: structural "
                f"{dup_candidate.structural_similarity:.2f}, KPI {dup_candidate.kpi_similarity:.2f}, title/context "
                f"{dup_candidate.semantic_similarity:.2f}) with existing asset {dup_asset_id}{lc_note}. The score is driven by shared "
                f"semantic-model and KPI evidence, not by title similarity alone. Creating another dashboard would increase report "
                f"sprawl, so the recommended path is to consolidate requirements into this shared asset.{rejected_note}{security_note}"
            )

            return DecisionResult(
                decision=DecisionType.CONSOLIDATE,
                confidence=0.88,
                primary_recommendation=f"Consolidate requirements into existing duplicate candidate {dup_asset_id}.",
                rationale=rationale,
                target_asset_ids=[dup_asset_id],
                target_model_ids=[discovery.exact_matches[0].model_id] if discovery.exact_matches and discovery.exact_matches[0].model_id else [],
                alternatives=[
                    DecisionAlternative(
                        action="MODIFY",
                        target_id=dup_asset_id,
                        pros="Retains single source of truth.",
                        cons="May require reconciling user permissions.",
                    ),
                    DecisionAlternative(
                        action="BUILD_NEW",
                        target_id=None,
                        pros="Independent customization.",
                        cons="Creates duplicate reporting and increases maintenance debt.",
                    ),
                ],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                ineligible_targets=consolidation_rejected,
                next_steps=[
                    f"Contact owner of asset {dup_asset_id} to schedule consolidation review.",
                    "Deprecate duplicate variants upon user alignment.",
                ],
            )

        # Option C: MODIFY Existing Semantic Model / Report
        # If an active asset or shared semantic model exists for the product, extend it!
        modify_rejected: List[Dict[str, Any]] = list(consolidation_rejected)
        relevant_asset = None
        pool = discovery.exact_matches if discovery.exact_matches else discovery.partial_matches
        pool = self._rank_modify_pool(pool, kpi_analysis, db)
        for candidate in pool:
            if not candidate.model_id:
                continue
            check = check_target(db, candidate.asset_id, "MODIFY")
            if check.eligible:
                relevant_asset = candidate
                break
            if all(r["asset_id"] != candidate.asset_id for r in modify_rejected):
                modify_rejected.append(check.as_dict())

        if relevant_asset is None and modify_rejected:
            names = ", ".join(r["asset_id"] for r in modify_rejected)
            return DecisionResult(
                decision=DecisionType.MODIFY,
                confidence=0.7,
                primary_recommendation=(
                    f"Existing assets cover this scope ({names}), but governance blocks acting on each of them. "
                    "Resolve the blockers before extending one; building new would duplicate them."
                ),
                rationale=" ".join(reason for r in modify_rejected for reason in r["reasons"]) + security_note,
                blockers=governance.blockers + [
                    reason for r in modify_rejected for reason in r["reasons"] if reason not in " ".join(governance.blockers)
                ],
                warnings=governance.warnings,
                human_approval_required=True,
                action_status=ActionStatus.BLOCKED,
                ineligible_targets=modify_rejected,
                next_steps=[f"Assign and verify an accountable owner for {names}, then ask BIOS to re-evaluate."],
            )

        if relevant_asset and relevant_asset.model_id:
            # Only blockers on this target, or request-level ones, stand in its way.
            target_blockers = self._blockers_affecting(governance.blockers, [relevant_asset.asset_id])
            has_critical_blockers = bool(target_blockers)
            blocker_prefix = f"Governance Blocker: {target_blockers[0]}. " if has_critical_blockers else ""
            rationale = (
                f"{blocker_prefix}Existing asset {relevant_asset.asset_id} ('{relevant_asset.asset_name}') and shared semantic "
                f"model {relevant_asset.model_id} already serve {relevant_asset.product_scope}. "
                "Rather than building a disconnected new report, the optimal path is to extend the existing "
                f"report or add requested measures to the shared semantic model.{security_note}"
            )
            requested_scope = expand_market_scope(intent.markets, db) if intent.markets else set()
            if requested_scope and relevant_asset.market_scope.lower() not in requested_scope and relevant_asset.market_scope.lower() != "global":
                rationale += (
                    f" Note: {relevant_asset.asset_id} currently covers {relevant_asset.market_scope}, not "
                    f"{', '.join(intent.markets)}; no existing asset covers the requested market, so the change extends its "
                    "market scope. If the owner declines, BUILD_NEW on the same shared model is the governed alternative."
                )

            primary_rec = (
                f"Resolve governance blocker ({target_blockers[0]}) then extend existing asset {relevant_asset.asset_id}."
                if has_critical_blockers
                else f"Extend existing asset {relevant_asset.asset_id} and shared model {relevant_asset.model_id}."
            )

            next_steps = [
                f"Submit change request to owner of model {relevant_asset.model_id}.",
                "Implement missing DAX measures for canonical KPIs.",
                "Test country-level slicing in dev workspace.",
            ]
            if has_critical_blockers:
                next_steps.insert(0, f"Resolve governance blocker: {target_blockers[0]}")

            return DecisionResult(
                decision=DecisionType.MODIFY,
                confidence=0.84 if not has_critical_blockers else 0.72,
                primary_recommendation=primary_rec,
                rationale=rationale,
                target_asset_ids=[relevant_asset.asset_id],
                target_model_ids=[relevant_asset.model_id],
                alternatives=[
                    DecisionAlternative(
                        action="BUILD_NEW",
                        target_id=None,
                        pros="Greenfield build with no legacy constraints.",
                        cons="Creates duplicate model logic and violates reuse guidelines.",
                    ),
                    DecisionAlternative(
                        action="REUSE",
                        target_id=relevant_asset.asset_id,
                        pros="Immediate zero-effort access.",
                        cons="Does not currently contain all requested measures.",
                    ),
                ],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                ineligible_targets=modify_rejected,
                next_steps=next_steps,
            )

        # Option D: MIGRATE Legacy Asset
        if migration_candidates:
            cand = migration_candidates[0]
            rationale = (
                f"Found legacy Tableau migration candidate {cand.source_asset_id} in {cand.product_scope} "
                f"(status: '{cand.status}', recommended path: '{cand.recommended_path_candidate}'). "
                f"Instead of building a separate asset, execute the planned migration of {cand.source_asset_id} "
                f"onto target semantic model {cand.candidate_target_model_id}."
            )

            return DecisionResult(
                decision=DecisionType.MIGRATE,
                confidence=0.82,
                primary_recommendation=f"Execute migration of legacy asset {cand.source_asset_id} onto model {cand.candidate_target_model_id}.",
                rationale=rationale,
                target_asset_ids=[cand.source_asset_id],
                target_model_ids=[cand.candidate_target_model_id],
                alternatives=[],
                blockers=governance.blockers,
                warnings=governance.warnings,
                human_approval_required=True,
                next_steps=[
                    f"Initiate migration workflow for {cand.source_asset_id}.",
                    "Validate metric parity against Tableau benchmark.",
                ],
            )

        # Option E: BUILD_NEW (Only when all above alternatives are exhausted)
        rationale = (
            f"Discovery searched all {discovery.total_searched} analytics assets, their semantic models and the migration backlog, "
            f"and found no existing asset covering {', '.join(intent.products) or 'the requested scope'} in "
            f"{', '.join(intent.markets) or 'the requested markets'}. "
            "Building a new analytics asset is justified, provided it connects to a shared semantic model, "
            "consumes approved canonical KPIs, and has an active owner assigned."
        )

        return DecisionResult(
            decision=DecisionType.BUILD_NEW,
            confidence=0.78,
            primary_recommendation="Build new governed analytics asset on shared semantic model.",
            rationale=rationale,
            target_asset_ids=[],
            target_model_ids=[],
            alternatives=[],
            blockers=governance.blockers,
            warnings=governance.warnings,
            human_approval_required=True,
            next_steps=[
                "Assign designated active business owner.",
                "Select or create certified shared semantic model.",
                "Map measures strictly to approved canonical KPIs.",
            ],
        )


def _title_mentions(title: str, metric: KpiMatch) -> bool:
    """Whole-phrase match, so 'net sales' doesn't match a title like 'Gross-to-Net Final'."""
    terms = (metric.requested_metric, metric.matched_kpi_name or "")
    return any(term and re.search(rf"\b{re.escape(term)}\b", title, re.IGNORECASE) for term in terms)


def _metric_names(metrics: List[KpiMatch]) -> str:
    return ", ".join(f"{m.matched_kpi_name} ({m.matched_kpi_id})" for m in metrics)


def _bounded(items: List[str]) -> List[str]:
    """Keep the narrative prompt inside the context window. Full lists stay on the decision."""
    return [item[:_MAX_NARRATIVE_ITEM_CHARS] for item in items[:_MAX_NARRATIVE_ITEMS]]

