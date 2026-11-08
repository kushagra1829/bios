"""
Answers to migration and retirement questions, read from Migration_Backlog and the catalog.

Migration_Backlog.recommended_path_candidate is a synthetic scenario input, not an official
decision, so every row is presented as a candidate path that needs human approval. Redundant
and untrusted assets are never presented as straight 1:1 migrations: CONSOLIDATE_BEFORE_MIGRATION,
RETIRE and HUMAN_REVIEW keep their own groups, and critical governance findings are attached.
"""
import re
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.agents.answering.governance_answers import ACTIVE, _expand_markets
from backend.app.agents.schemas import BusinessIntent, MigrationAnswer
from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.models.governance import GovernanceFindings, MigrationBacklog

PATH_LABELS = {
    "MIGRATE": "Migrate directly to Power BI",
    "CONSOLIDATE_BEFORE_MIGRATION": "Consolidate before migrating",
    "REBUILD_ON_SHARED_MODEL": "Rebuild on a shared semantic model (modify)",
    "RETIRE": "Retire instead of migrating",
    "HUMAN_REVIEW": "Needs human review before any path",
}
PATH_ORDER = ["MIGRATE", "CONSOLIDATE_BEFORE_MIGRATION", "REBUILD_ON_SHARED_MODEL", "RETIRE", "HUMAN_REVIEW"]
APPROVAL_NOTE = (
    "These are recommendations. Migrating, consolidating or retiring an asset is a consequential lifecycle action: "
    "it needs an approval request signed off by the asset's accountable owner (RULE-008 requires the rationale)."
)


class MigrationQuestionAnswerer:
    def answer(self, prompt: str, intent: BusinessIntent, db: Session) -> MigrationAnswer:
        markets, _ = _expand_markets(list(intent.markets), db)
        filters: Dict[str, Any] = {"products": list(intent.products), "market_scopes": sorted(markets)}
        asset_ids = [a for a in intent.asset_ids_mentioned if a.startswith("AST-")]

        path_filter: List[str] = []
        if re.search(r"\bconsolidat\w*\b", prompt, re.IGNORECASE):
            path_filter = ["CONSOLIDATE_BEFORE_MIGRATION"]
        elif re.search(r"\bretire\w*|retirement|decommission\w*|sunset\w*\b", prompt, re.IGNORECASE):
            path_filter = ["RETIRE"]
        elif re.search(r"\brebuild\w*\b", prompt, re.IGNORECASE):
            path_filter = ["REBUILD_ON_SHARED_MODEL"]
        elif re.search(r"\b(?:human\s+review|manual\s+review|needs?\s+review)\b", prompt, re.IGNORECASE):
            path_filter = ["HUMAN_REVIEW"]
        elif re.search(r"\bshould\s+be\s+migrated\b|\bcan\s+be\s+migrated\b|\bready\s+to\s+migrate\b|\bmigrate\s+directly\b|\bdirect\s+migration\b", prompt, re.IGNORECASE):
            path_filter = []  # show all paths: "should be migrated" is answered by separating direct migration from the rest
        if asset_ids:
            path_filter = []  # an asset-specific question gets that asset's record, whatever its path
        filters["paths"] = path_filter or "all"
        status = re.search(r"\b(not[_\s]started|in[_\s]progress|assessed)\b", prompt, re.IGNORECASE)
        if status:
            filters["status"] = status.group(1).lower().replace(" ", "_")

        assets = {a.asset_id: a for a in db.query(AnalyticsAssets).all()}
        owners = {o.owner_id: o for o in db.query(Owners).all()}
        critical = {}
        for f in db.query(GovernanceFindings).filter(GovernanceFindings.status.in_(ACTIVE), GovernanceFindings.severity == "critical").all():
            critical.setdefault(f.target_entity_id, []).append(f"{f.rule_id}: {f.title}")
        retirement_risk = {
            f.target_entity_id
            for f in db.query(GovernanceFindings).filter(GovernanceFindings.status.in_(ACTIVE), GovernanceFindings.rule_id == "RULE-008").all()
        }

        rows = db.query(MigrationBacklog).order_by(MigrationBacklog.source_asset_id).all()
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            if asset_ids and row.source_asset_id not in asset_ids:
                continue
            if filters["products"] and row.product_scope not in filters["products"]:
                continue
            if filters["market_scopes"] and row.market_scope not in filters["market_scopes"]:
                continue
            if path_filter and row.recommended_path_candidate not in path_filter:
                continue
            if filters.get("status") and row.status != filters["status"]:
                continue
            asset = assets.get(row.source_asset_id)
            owner = owners.get(asset.owner_id) if asset and asset.owner_id else None
            blockers = list(critical.get(row.source_asset_id, []))
            if row.recommended_path_candidate == "RETIRE" and row.source_asset_id in retirement_risk:
                blockers.append("RULE-008: asset has active usage; an impact assessment and sign-off are needed before retirement")
            groups.setdefault(row.recommended_path_candidate, []).append({
                "asset_id": row.source_asset_id,
                "asset_name": asset.asset_name if asset else None,
                "platform": asset.platform if asset else None,
                "product_scope": row.product_scope,
                "market_scope": row.market_scope,
                "recommended_path": row.recommended_path_candidate,
                "path_label": PATH_LABELS.get(row.recommended_path_candidate, row.recommended_path_candidate),
                "candidate_target_model_id": row.candidate_target_model_id,
                "complexity": row.complexity,
                "status": row.status,
                "reason": row.synthetic_reason,
                "owner_name": owner.owner_name if owner else None,
                "estimated_audience": asset.estimated_audience if asset else None,
                "governance_blockers": blockers,
                "action_status": "BLOCKED" if blockers else "REQUIRES_APPROVAL",
            })
        ordered = {path: groups[path] for path in PATH_ORDER if path in groups}
        total = sum(len(v) for v in ordered.values())

        # Retirement questions also cover the catalog's own lifecycle flag, kept as a separate group.
        lifecycle_retire: List[Dict[str, Any]] = []
        if path_filter == ["RETIRE"] and not asset_ids:
            for asset in sorted(assets.values(), key=lambda a: a.asset_id):
                if asset.lifecycle_status != "candidate_retire":
                    continue
                if filters["products"] and asset.product_scope not in filters["products"]:
                    continue
                if filters["market_scopes"] and asset.market_scope not in filters["market_scopes"]:
                    continue
                if re.search(r"\btableau\b", prompt, re.IGNORECASE) and asset.platform != "Tableau":
                    continue
                lifecycle_retire.append({
                    "asset_id": asset.asset_id, "asset_name": asset.asset_name, "platform": asset.platform,
                    "product_scope": asset.product_scope, "market_scope": asset.market_scope,
                    "lifecycle_status": asset.lifecycle_status, "estimated_audience": asset.estimated_audience,
                    "governance_blockers": list(critical.get(asset.asset_id, []))
                    + (["RULE-008: active usage; impact assessment and sign-off required"] if asset.asset_id in retirement_risk else []),
                })
            if lifecycle_retire:
                ordered["CATALOG_CANDIDATE_RETIRE"] = lifecycle_retire

        scope = " ".join(filter(None, ["/".join(filters["products"]), ", ".join(filters["market_scopes"])])) or "estate-wide"
        if asset_ids and total:
            item = next(iter(ordered.values()))[0]
            headline = (
                f"{item['asset_id']} ('{item['asset_name']}'): the migration backlog recommends '{item['path_label']}'"
                f" (status {item['status']}, complexity {item['complexity']}, target model {item['candidate_target_model_id']})."
                + (f" It is blocked by {'; '.join(item['governance_blockers'])}." if item["governance_blockers"] else "")
            )
        elif asset_ids:
            known = [a for a in asset_ids if a in assets]
            headline = (
                f"{', '.join(known)} has no Migration_Backlog record, so BIOS has no migration recommendation for it."
                if known else "The asset ID in the question is not in the analytics catalog."
            )
        elif path_filter == ["RETIRE"]:
            backlog_n = len(ordered.get("RETIRE", []))
            headline = (
                f"{backlog_n} {scope} Tableau asset(s) have a RETIRE path in the migration backlog, and "
                f"{len(lifecycle_retire)} {scope} asset(s) are flagged candidate_retire in the catalog."
            )
        elif total:
            counts = ", ".join(f"{len(v)} {PATH_LABELS[k].lower()}" for k, v in ordered.items() if k in PATH_LABELS)
            direct = ordered.get("MIGRATE", [])
            headline = (
                f"{total} {scope} Tableau asset(s) are in the migration backlog: {counts}. "
                + (f"Direct migration candidates: {', '.join(r['asset_id'] for r in direct)}." if direct else "None is a direct 1:1 migration candidate.")
            )
        else:
            headline = f"No {scope} assets match in the migration backlog."

        explanation = [
            "Paths come from Migration_Backlog.recommended_path_candidate, a synthetic scenario input rather than an official decision.",
            "RULE-006 (Do not migrate waste): consolidation and retirement candidates are not migrated 1:1.",
        ]
        blocked = [r["asset_id"] for v in ordered.values() for r in v if r.get("governance_blockers")]
        if blocked:
            explanation.append(f"Blocked by governance until resolved: {', '.join(dict.fromkeys(blocked))}.")
        return MigrationAnswer(
            status="ANSWERED" if (total or lifecycle_retire) else "NO_MATCH",
            headline=headline,
            groups=ordered,
            total_matching=total + len(lifecycle_retire),
            explanation=explanation,
            filters=filters,
            approval_note=APPROVAL_NOTE,
            source={"table": "migration_backlog + analytics_assets + governance_findings"},
        )
