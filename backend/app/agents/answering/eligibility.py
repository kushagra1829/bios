"""
Whether an existing asset may be the target of a recommended action.

The backend governance findings are authoritative. An asset whose findings forbid an action can
still be shown as evidence, but it is never offered as an actionable target:

  - no accountable owner (RULE-003 critical): cannot be extended, modified, consolidated into,
    reused as a governed target, retired or migrated until an owner is assigned and verified
  - inactive owner (RULE-003 high): changes need an active owner's authority (N4), so change
    actions are blocked until the asset is reassigned; read-only reuse is allowed with a warning
  - any other critical persisting finding on the asset: the action is blocked until resolved
  - lifecycle candidate_retire / legacy: reuse needs the owner to confirm the asset is staying
"""
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.models.governance import GovernanceFindings

CHANGE_ACTIONS = {"MODIFY", "CONSOLIDATE", "RETIRE", "MIGRATE"}
ACTIVE_FINDING_STATUSES = ("open", "persisting")


@dataclass
class TargetCheck:
    asset_id: str
    exists: bool
    eligible: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rule_ids: List[str] = field(default_factory=list)
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_status: Optional[str] = None
    lifecycle_status: Optional[str] = None
    endorsement: Optional[str] = None
    critical_finding_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "eligible": self.eligible,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "rule_ids": self.rule_ids,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "owner_status": self.owner_status,
            "lifecycle_status": self.lifecycle_status,
            "endorsement": self.endorsement,
            "critical_finding_ids": self.critical_finding_ids,
        }


def check_target(db: Session, asset_id: str, action: str) -> TargetCheck:
    """Deterministic eligibility of one asset for one action (REUSE, MODIFY, CONSOLIDATE, RETIRE, MIGRATE)."""
    asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_id).first()
    if asset is None:
        return TargetCheck(asset_id=asset_id, exists=False, eligible=False, reasons=[f"{asset_id} is not in the analytics catalog."])

    owner = db.query(Owners).filter(Owners.owner_id == asset.owner_id).first() if asset.owner_id else None
    check = TargetCheck(
        asset_id=asset_id,
        exists=True,
        eligible=True,
        owner_id=asset.owner_id,
        owner_name=owner.owner_name if owner else None,
        owner_status=owner.status if owner else None,
        lifecycle_status=asset.lifecycle_status,
        endorsement=asset.endorsement,
    )

    if asset.owner_id is None:
        check.eligible = False
        check.rule_ids.append("RULE-003")
        check.reasons.append(
            f"{asset_id} has no accountable owner (RULE-003). It cannot be {_verb(action)} until an owner is assigned and verified."
        )
    elif owner is not None and owner.status != "active":
        if action in CHANGE_ACTIONS:
            check.eligible = False
            check.rule_ids.append("RULE-003")
            check.reasons.append(
                f"{asset_id}'s owner {owner.owner_name} ({owner.owner_id}) is {owner.status}, so nobody holds the authority to approve "
                f"changes (RULE-003, N4). Reassign an active owner first."
            )
        else:
            check.warnings.append(f"{asset_id}'s owner {owner.owner_name} is {owner.status}; reassign before relying on it long term (RULE-003).")

    critical = (
        db.query(GovernanceFindings)
        .filter(
            GovernanceFindings.target_entity_id == asset_id,
            GovernanceFindings.status.in_(ACTIVE_FINDING_STATUSES),
            GovernanceFindings.severity == "critical",
        )
        .all()
    )
    for finding in critical:
        check.critical_finding_ids.append(finding.finding_id)
        if finding.rule_id == "RULE-003" and asset.owner_id is None:
            continue  # already explained above
        check.eligible = False
        if finding.rule_id not in check.rule_ids:
            check.rule_ids.append(finding.rule_id)
        check.reasons.append(f"{finding.rule_id} critical finding on {asset_id}: {finding.title}.")

    if action == "RETIRE":
        # RULE-008 (Explain every lifecycle action): an asset with active usage can't be retired until an
        # impact assessment, a successor and executive sign-off exist. Approval alone doesn't clear it.
        risk = (
            db.query(GovernanceFindings)
            .filter(
                GovernanceFindings.target_entity_id == asset_id,
                GovernanceFindings.rule_id == "RULE-008",
                GovernanceFindings.status.in_(ACTIVE_FINDING_STATUSES),
            )
            .all()
        )
        for finding in risk:
            check.eligible = False
            if "RULE-008" not in check.rule_ids:
                check.rule_ids.append("RULE-008")
            check.reasons.append(f"RULE-008 on {asset_id}: {finding.title}. {finding.recommended_action}")

    if action in ("REUSE", "CONSOLIDATE") and asset.lifecycle_status in ("candidate_retire", "retired", "decommissioned"):
        check.eligible = False
        if "RULE-008" not in check.rule_ids:
            check.rule_ids.append("RULE-008")
        check.reasons.append(
            f"{asset_id} has lifecycle status '{asset.lifecycle_status}' (candidate for retirement / decommission). "
            f"Retiring or decommissioned assets cannot be recommended as governed targets for {action.lower()} (RULE-008)."
        )
    elif action == "MODIFY" and asset.lifecycle_status in ("retired", "decommissioned"):
        check.eligible = False
        if "RULE-008" not in check.rule_ids:
            check.rule_ids.append("RULE-008")
        check.reasons.append(
            f"{asset_id} has lifecycle status '{asset.lifecycle_status}'. "
            f"Decommissioned or retired assets cannot be targeted for modification (RULE-008)."
        )
    elif action in ("REUSE", "MODIFY") and asset.lifecycle_status != "active":
        check.warnings.append(
            f"{asset_id} has lifecycle status '{asset.lifecycle_status}', so its owner must confirm it will stay available before you rely on it."
        )
    return check


def _verb(action: str) -> str:
    return {
        "MODIFY": "safely extended or modified",
        "CONSOLIDATE": "used as a consolidation target",
        "REUSE": "used as a governed reuse target",
        "RETIRE": "retired, because no accountable owner can sign off the retirement",
        "MIGRATE": "migrated",
    }.get(action, "acted on")
