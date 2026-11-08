"""
Answers to governance questions, read from the authoritative governance findings and catalog.

The question is answered first ("AST-0268 is blocked because..."), then the supporting findings.
Nothing here re-evaluates a rule: findings come from the deterministic governance engine's
persisted run, and asset, owner, KPI and model facts come straight from the catalog tables.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.app.agents.schemas import BusinessIntent, FindingView, GovernanceAnswer
from backend.app.models.core import AnalyticsAssets, LineageEdges, Owners, SemanticModels
from backend.app.models.domain import Markets
from backend.app.models.governance import AssetKpiMap, GovernanceFindings, GovernanceRules, KpiCatalog

ACTIVE = ("open", "persisting")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
MAX_LISTED = 25

RULE_CONSEQUENCE = {
    "RULE-001": "Reuse an existing trusted asset before building another one.",
    "RULE-002": "Remap to approved canonical KPIs before release; unapproved high-criticality KPIs cannot go to production.",
    "RULE-003": "Without an accountable owner the asset cannot be safely extended, modified, consolidated into, migrated or retired.",
    "RULE-004": "Register lineage before deploying or retiring, so downstream impact is known.",
    "RULE-005": "A high-reach asset needs certification review or restricted distribution.",
    "RULE-006": "Do not migrate waste: retire or consolidate before migrating.",
    "RULE-007": "Fix semantic-model naming, dates or measures before AI/natural-language use.",
    "RULE-008": "Every lifecycle action needs an explanation; an asset with active usage needs an impact assessment and sign-off before retirement.",
}

KIND_PATTERNS: List[Tuple[str, str]] = [
    ("INACTIVE_OWNER", r"\binactive\s+owners?\b|\bowners?\s+(?:is|are)\s+inactive\b|\bdeparted\s+owners?\b"),
    ("UNOWNED", r"\bno\s+(?:accountable\s+|assigned\s+|active\s+)?owners?\b|\bunowned\b|\bwithout\s+(?:an?\s+)?(?:accountable\s+)?owners?\b|"
                r"\bmissing\s+(?:an?\s+)?(?:accountable\s+)?owners?\b|\bownerless\b|\borphan(?:ed)?\s+(?:assets?|reports?|dashboards?)\b|\bnobody\s+owns\b|\bno\s+one\s+owns\b"),
    ("KPI_CONFLICTS", r"\b(?:which|list|show|what)\b[^?]*\bkpis?\b[^?]*\b(?:conflict\w*|variants?|duplicates?|unapproved|non-canonical|not\s+approved|local)\b(?![^?]*\b(?:assets?|reports?|dashboards?|workbooks?|apps?)\b)"),
    ("NON_CANONICAL", r"\bnon-canonical\b|\bnot\s+canonical\b|\bunapproved\s+kpis?\b|\blocal\s+kpis?\b|\bkpi\s+(?:variants?|drift)\b|\bshadow\s+(?:kpis?|metrics?)\b"),
    ("POOR_LINEAGE", r"\blineage\b"),
    ("HIGH_REACH_UNENDORSED", r"\bhigh[-\s]reach\b|\baudience\s+reach\b|\bnot\s+endorsed\b|\bunendorsed\b|\bwithout\s+endorsement\b|\blarge\s+audience\b"),
    ("AI_READINESS", r"\bai[-\s]read\w*\b|\bai\s+readiness\b|\bpoor\s+names\b|\bambiguous\s+dates\b|\bimplicit\s+measures\b|\bnatural[-\s]language\s+read\w*\b|\bcopilot\b"),
    ("MODEL_REFRESH", r"\brefresh\w*\b"),
    ("DUPLICATE_TITLES", r"\bduplicate\s+(?:titles?|names?)\b|\bsame\s+(?:title|name)\b"),
    ("RETIREMENT_RISK", r"\bretirement\s+risk\b|\bexplainab\w+\b|\bunjustified\s+retire\w*\b"),
    ("CERTIFIED", r"\bcertified\b|\bpromoted\b|\bendorsed\b|\btrusted\b"),
]


def _severity_key(severity: str) -> int:
    return SEVERITY_ORDER.get((severity or "").lower(), 9)


def _expand_markets(markets: List[str], db: Session) -> Tuple[Set[str], bool]:
    """Asset market scopes the requested markets select, and whether 'Global' was asked for."""
    if not markets:
        return set(), False
    region_members: Dict[str, Set[str]] = {}
    for market_id, region in db.query(Markets.market_id, Markets.region).all():
        region_members.setdefault((region or "").lower(), set()).add(market_id)
    scope: Set[str] = set()
    wants_global = False
    for market in markets:
        if market.lower() == "global":
            wants_global = True
            scope.add("Global")
        elif market.lower() in region_members:
            scope |= region_members[market.lower()]
        else:
            scope.add(market)
    return scope, wants_global


class GovernanceQuestionAnswerer:
    def answer(self, prompt: str, intent: BusinessIntent, db: Session) -> GovernanceAnswer:
        rules = {r.rule_id: r.rule_name for r in db.query(GovernanceRules).all()}
        asset_ids = [a for a in intent.asset_ids_mentioned if a.startswith("AST-")]
        model_ids = [a for a in intent.asset_ids_mentioned if a.startswith("SM-")]
        if asset_ids:
            return self._asset_status(prompt, asset_ids, db, rules)
        if model_ids:
            return self._model_status(model_ids, db, rules)

        kpi = self._kpi_named(prompt, db)
        if kpi is not None and re.search(r"\b(?:defin\w*|approved|approval|canonical|status|mean|meaning|owner|owns|unit|conflict\w*|variants?|what\s+is)\b", prompt, re.IGNORECASE):
            return self._kpi_definition(kpi, db)

        kind = next((k for k, pattern in KIND_PATTERNS if re.search(pattern, prompt, re.IGNORECASE)), "GOVERNANCE_SUMMARY")
        filters = self._filters(prompt, intent, db)
        if kind == "KPI_CONFLICTS":
            return self._kpi_conflicts(prompt, db)
        if kind == "AI_READINESS":
            return self._ai_readiness(filters, db, rules)
        if kind == "MODEL_REFRESH":
            return self._model_refresh(filters, db)
        if kind == "CERTIFIED":
            return self._certified(prompt, filters, db)
        rule_for_kind = {
            "UNOWNED": ("RULE-003", "critical"),
            "INACTIVE_OWNER": ("RULE-003", "high"),
            "NON_CANONICAL": ("RULE-002", None),
            "POOR_LINEAGE": ("RULE-004", None),
            "HIGH_REACH_UNENDORSED": ("RULE-005", None),
            "DUPLICATE_TITLES": ("RULE-001", None),
            "RETIREMENT_RISK": ("RULE-008", None),
        }
        if kind in rule_for_kind:
            rule_id, severity = rule_for_kind[kind]
            return self._finding_list(kind, rule_id, severity, filters, db, rules)
        return self._summary(filters, db, rules)

    # ------------------------------------------------------------------ filters
    def _filters(self, prompt: str, intent: BusinessIntent, db: Session) -> Dict[str, Any]:
        products = [p for p in intent.products]
        markets, wants_global = _expand_markets(list(intent.markets), db)
        platform = None
        if re.search(r"\btableau\b", prompt, re.IGNORECASE):
            platform = "Tableau"
        elif re.search(r"\bpower\s*bi\b", prompt, re.IGNORECASE) and not re.search(r"\bto\s+power\s*bi\b", prompt, re.IGNORECASE):
            platform = "Power BI"
        lifecycle = None
        if re.search(r"\blegacy\b", prompt, re.IGNORECASE):
            lifecycle = "legacy"
        elif re.search(r"\bactive\s+(?:assets?|reports?|dashboards?)\b", prompt, re.IGNORECASE):
            lifecycle = "active"
        return {
            "products": products,
            "market_scopes": sorted(markets),
            "platform": platform,
            "lifecycle_status": lifecycle,
            "note": "Asset-type words (dashboard, report, workbook, app) are read as 'any analytics asset'; platform words filter.",
        }

    @staticmethod
    def _asset_matches(asset: AnalyticsAssets, filters: Dict[str, Any]) -> bool:
        if filters["products"] and asset.product_scope not in filters["products"]:
            return False
        if filters["market_scopes"] and asset.market_scope not in filters["market_scopes"]:
            return False
        if filters["platform"] and asset.platform != filters["platform"]:
            return False
        if filters["lifecycle_status"] and asset.lifecycle_status != filters["lifecycle_status"]:
            return False
        return True

    @staticmethod
    def _asset_row(asset: AnalyticsAssets, owner: Optional[Owners], **extra: Any) -> Dict[str, Any]:
        return {
            "asset_id": asset.asset_id,
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "platform": asset.platform,
            "product_scope": asset.product_scope,
            "market_scope": asset.market_scope,
            "endorsement": asset.endorsement,
            "lifecycle_status": asset.lifecycle_status,
            "estimated_audience": asset.estimated_audience,
            "owner_id": asset.owner_id,
            "owner_name": owner.owner_name if owner else None,
            "owner_status": owner.status if owner else None,
            **extra,
        }

    @staticmethod
    def _scope_words(filters: Dict[str, Any]) -> str:
        parts = []
        if filters["platform"]:
            parts.append(filters["platform"])
        if filters["products"]:
            parts.append("/".join(filters["products"]))
        text = " ".join(parts)
        if filters["market_scopes"]:
            text += f" in {', '.join(filters['market_scopes'])}"
        if filters["lifecycle_status"]:
            text = f"{filters['lifecycle_status']} {text}"
        return text.strip()

    # ------------------------------------------------------------------ question kinds
    def _finding_list(self, kind, rule_id, severity, filters, db, rules) -> GovernanceAnswer:
        query = db.query(GovernanceFindings).filter(
            GovernanceFindings.rule_id == rule_id,
            GovernanceFindings.status.in_(ACTIVE),
            GovernanceFindings.target_entity_type == "asset",
        )
        if severity:
            query = query.filter(GovernanceFindings.severity == severity)
        findings = query.all()
        assets = {a.asset_id: a for a in db.query(AnalyticsAssets).all()}
        owners = {o.owner_id: o for o in db.query(Owners).all()}
        rows: List[Dict[str, Any]] = []
        for f in sorted(findings, key=lambda f: (_severity_key(f.severity), f.target_entity_id)):
            asset = assets.get(f.target_entity_id)
            if asset is None or not self._asset_matches(asset, filters):
                continue
            rows.append(self._asset_row(
                asset, owners.get(asset.owner_id),
                finding_id=f.finding_id, rule_id=f.rule_id, severity=f.severity, finding=f.title, required_action=f.recommended_action,
            ))
        description = {
            "UNOWNED": "have no accountable owner",
            "INACTIVE_OWNER": "have an inactive owner",
            "NON_CANONICAL": "use non-canonical KPIs",
            "POOR_LINEAGE": "have lineage defects",
            "HIGH_REACH_UNENDORSED": "are unendorsed despite high audience reach",
            "DUPLICATE_TITLES": "have duplicate titles",
            "RETIREMENT_RISK": "carry a retirement-explainability risk (active usage)",
        }[kind]
        scope = self._scope_words(filters) or "estate-wide"
        count = len(rows)
        headline = (
            f"{count} {scope} asset{'s' if count != 1 else ''} {description}"
            + (f": {', '.join(r['asset_id'] for r in rows[:8])}{' and more' if count > 8 else ''}." if count else ".")
        )
        explanation = [f"{rule_id} ({rules.get(rule_id, '')}): {RULE_CONSEQUENCE.get(rule_id, '')}"]
        if kind == "HIGH_REACH_UNENDORSED":
            explanation.append(
                "RULE-005 thresholds: unendorsed assets with audience above 500 are flagged (high severity at 1,000 or more), "
                "and self-service assets with audience of 250 or more need BI governance review."
            )
        if kind == "UNOWNED":
            explanation.append("These are the RULE-003 critical findings: Analytics_Assets.owner_id is empty.")
        return GovernanceAnswer(
            status="ANSWERED" if count else "NO_MATCH",
            question_kind=kind,
            headline=headline,
            explanation=explanation,
            rules=[{"rule_id": rule_id, "rule_name": rules.get(rule_id, "")}],
            assets=rows[:MAX_LISTED],
            total_matching=count,
            filters=filters,
            source={"table": "governance_findings", "status": list(ACTIVE), "rule_id": rule_id, "severity": severity},
        )

    def _asset_status(self, prompt: str, asset_ids: List[str], db: Session, rules: Dict[str, str]) -> GovernanceAnswer:
        rows: List[Dict[str, Any]] = []
        views: List[FindingView] = []
        headlines: List[str] = []
        explanation: List[str] = []
        missing: List[str] = []
        for asset_id in asset_ids:
            asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == asset_id).first()
            if asset is None:
                missing.append(asset_id)
                continue
            owner = db.query(Owners).filter(Owners.owner_id == asset.owner_id).first() if asset.owner_id else None
            model = db.query(SemanticModels).filter(SemanticModels.model_id == asset.model_id).first()
            findings = (
                db.query(GovernanceFindings)
                .filter(GovernanceFindings.target_entity_id == asset_id, GovernanceFindings.status.in_(ACTIVE))
                .all()
            )
            findings.sort(key=lambda f: (_severity_key(f.severity), f.rule_id))
            kpis = (
                db.query(KpiCatalog.kpi_id, KpiCatalog.kpi_name, KpiCatalog.approval_status)
                .join(AssetKpiMap, AssetKpiMap.kpi_id == KpiCatalog.kpi_id)
                .filter(AssetKpiMap.asset_id == asset_id)
                .all()
            )
            upstream = [e.source_id for e in db.query(LineageEdges).filter(LineageEdges.target_id == asset_id).all()]
            downstream = [e.target_id for e in db.query(LineageEdges).filter(LineageEdges.source_id == asset_id).all()]
            rows.append(self._asset_row(
                asset, owner,
                model_id=asset.model_id,
                model_name=model.model_name if model else None,
                model_endorsement=model.endorsement if model else None,
                model_ai_readiness=model.ai_readiness if model else None,
                kpis=[{"kpi_id": k, "kpi_name": n, "approval_status": s} for k, n, s in kpis],
                lineage_upstream=upstream,
                lineage_downstream=downstream,
                finding_count=len(findings),
            ))
            blockers = [f for f in findings if f.severity == "critical"]
            for f in findings:
                views.append(FindingView(
                    rule_id=f.rule_id,
                    severity=f.severity.upper(),
                    asset_id=asset_id,
                    kind="BLOCKER" if f.severity == "critical" else "WARNING",
                    effect="PREVENTS_ACTION" if f.severity == "critical" else ("REQUIRES_REVIEW" if f.severity == "high" else "INFORMATIONAL"),
                    message=f.title,
                    required_action=f.recommended_action or "",
                    finding_ids=[f.finding_id],
                    sources=[f.finding_id],
                    affects_target=True,
                ))
            wants_owner = re.search(r"\bwho\s+owns\b|\bowner\b", prompt, re.IGNORECASE)
            wants_lineage = re.search(r"\blineage\b|\bdownstream\b|\bupstream\b|\bdepend", prompt, re.IGNORECASE)
            owner_text = (
                f"owned by {owner.owner_name} ({owner.owner_id}, {owner.role}, {owner.status})" if owner else "has no accountable owner"
            )
            if wants_owner and not re.search(r"\bblock", prompt, re.IGNORECASE):
                headlines.append(f"{asset_id} ('{asset.asset_name}') is {owner_text}.")
            elif wants_lineage:
                headlines.append(
                    f"{asset_id} ('{asset.asset_name}') depends on {', '.join(upstream) or 'no recorded upstream source'}"
                    f" and feeds {', '.join(downstream) or 'no recorded downstream asset'}."
                )
            elif blockers:
                reasons = "; ".join(f"{f.title} ({f.rule_id}, critical)" for f in blockers)
                headlines.append(f"{asset_id} ('{asset.asset_name}') is blocked: {reasons}.")
                for f in blockers:
                    explanation.append(f"{f.rule_id} ({rules.get(f.rule_id, '')}): {RULE_CONSEQUENCE.get(f.rule_id, '')}")
                if any(f.rule_id == "RULE-003" for f in blockers):
                    explanation.append(
                        f"Assign an accountable, active owner to {asset_id}; BIOS re-evaluates the asset once the owner is assigned and verified."
                    )
            else:
                headlines.append(
                    f"{asset_id} ('{asset.asset_name}') has no blocking (critical) findings; it has {len(findings)} other active finding(s). "
                    f"It is {owner_text}, {asset.endorsement} endorsement, lifecycle '{asset.lifecycle_status}'."
                )
            others = [f for f in findings if f.severity != "critical"]
            if others:
                explanation.append(
                    "Other findings: " + "; ".join(f"{f.rule_id} {f.severity}: {f.title}" for f in others[:6]) + "."
                )
        if missing and not rows:
            return GovernanceAnswer(
                status="NOT_FOUND",
                question_kind="ASSET_STATUS",
                headline="The asset ID in the question is not in the analytics catalog, so BIOS has no governance record for it.",
                source={"table": "analytics_assets"},
            )
        if missing:
            explanation.append(f"{len(missing)} other asset ID(s) in the question are not in the catalog.")
        return GovernanceAnswer(
            status="ANSWERED",
            question_kind="ASSET_STATUS",
            headline=" ".join(headlines),
            explanation=explanation,
            rules=[{"rule_id": r, "rule_name": rules.get(r, "")} for r in sorted({v.rule_id for v in views})],
            assets=rows,
            total_matching=len(rows),
            findings=views,
            source={"table": "governance_findings + analytics_assets + owners + asset_kpi_map + lineage_edges", "status": list(ACTIVE)},
        )

    def _model_status(self, model_ids: List[str], db: Session, rules: Dict[str, str]) -> GovernanceAnswer:
        rows = []
        views: List[FindingView] = []
        for model_id in model_ids:
            model = db.query(SemanticModels).filter(SemanticModels.model_id == model_id).first()
            if model is None:
                continue
            findings = db.query(GovernanceFindings).filter(GovernanceFindings.target_entity_id == model_id, GovernanceFindings.status.in_(ACTIVE)).all()
            dependents = db.query(AnalyticsAssets.asset_id).filter(AnalyticsAssets.model_id == model_id).all()
            rows.append({
                "model_id": model.model_id, "model_name": model.model_name, "product_scope": model.product_scope,
                "region_scope": model.region_scope, "endorsement": model.endorsement, "refresh_status": model.refresh_status,
                "ai_readiness": model.ai_readiness, "ai_issue_pattern": model.ai_issue_pattern, "owner_id": model.owner_id,
                "dependent_assets": [d for (d,) in dependents],
            })
            for f in findings:
                views.append(FindingView(rule_id=f.rule_id, severity=f.severity.upper(), asset_id=model_id,
                                         kind="BLOCKER" if f.severity == "critical" else "WARNING",
                                         effect="PREVENTS_ACTION" if f.severity == "critical" else "REQUIRES_REVIEW",
                                         message=f.title, required_action=f.recommended_action or "", finding_ids=[f.finding_id], affects_target=True))
        if not rows:
            return GovernanceAnswer(status="NOT_FOUND", question_kind="MODEL_STATUS", headline="The semantic model ID in the question is not in the catalog.")
        m = rows[0]
        headline = (
            f"{m['model_id']} ('{m['model_name']}') is {m['endorsement']}, refresh {m['refresh_status']}, AI readiness "
            f"{m['ai_readiness']} ({m['ai_issue_pattern']}), used by {len(m['dependent_assets'])} asset(s); {len(views)} active finding(s)."
        )
        return GovernanceAnswer(status="ANSWERED", question_kind="MODEL_STATUS", headline=headline, assets=rows, total_matching=len(rows),
                                findings=views, source={"table": "semantic_models + governance_findings"})

    @staticmethod
    def _kpi_named(prompt: str, db: Session) -> Optional[List[KpiCatalog]]:
        kpis = db.query(KpiCatalog).all()
        id_match = re.search(r"\bKPI-\d{3}\b", prompt, re.IGNORECASE)
        if id_match:
            found = [k for k in kpis if k.kpi_id == id_match.group(0).upper()]
            return found or None
        best: List[KpiCatalog] = []
        best_len = 0
        for k in kpis:
            pattern = r"(?<!\w)" + r"[\s-]+".join(re.escape(p) for p in k.kpi_name.split()) + r"(?!\w)"
            if re.search(pattern, prompt, re.IGNORECASE):
                if len(k.kpi_name) > best_len:
                    best, best_len = [k], len(k.kpi_name)
                elif len(k.kpi_name) == best_len:
                    best.append(k)
        return best or None

    def _kpi_definition(self, kpis: List[KpiCatalog], db: Session) -> GovernanceAnswer:
        primary = kpis[0]
        root = re.sub(r"\s+(?:Local|v2|Legacy|Mgmt|Adjusted)$", "", primary.kpi_name)
        family = db.query(KpiCatalog).filter(KpiCatalog.kpi_name.like(f"{root}%")).order_by(KpiCatalog.kpi_id).all()
        owner = db.query(Owners).filter(Owners.owner_id == primary.owner_id).first()
        rows = [
            {"kpi_id": k.kpi_id, "kpi_name": k.kpi_name, "domain": k.domain, "unit": k.unit, "definition_status": k.definition_status,
             "approval_status": k.approval_status, "default_frequency": k.default_frequency, "business_criticality": k.business_criticality,
             "owner_id": k.owner_id, "description": k.description}
            for k in family
        ]
        same_name = [k.kpi_id for k in kpis]
        canonical = next((k for k in family if k.definition_status == "canonical"), None)
        status_text = (
            f"the approved canonical definition" if primary.definition_status == "canonical" and primary.approval_status == "approved"
            else f"NOT the canonical definition: it is '{primary.definition_status}' with approval status '{primary.approval_status}'"
        )
        headline = (
            f"{primary.kpi_id} {primary.kpi_name} is {status_text}. Domain {primary.domain}, unit {primary.unit}, "
            f"{primary.default_frequency}, {primary.business_criticality} criticality, owner {owner.owner_name if owner else primary.owner_id}."
        )
        explanation = [
            f"The KPI catalog's description text is: \"{primary.description}\". It records no calculation formula, so BIOS does not invent one."
        ]
        if len(same_name) > 1:
            explanation.append(f"The catalog has {len(same_name)} KPIs named '{primary.kpi_name}' ({', '.join(same_name)}); they are separate entries.")
        if canonical and canonical.kpi_id != primary.kpi_id:
            explanation.append(f"Use {canonical.kpi_id} {canonical.kpi_name} (canonical, {canonical.approval_status}) instead (RULE-002).")
        variants = [k for k in family if k.definition_status != "canonical"]
        if variants:
            explanation.append(
                f"{len(variants)} non-canonical variant(s) exist: "
                + "; ".join(f"{k.kpi_id} {k.kpi_name} ({k.definition_status}, {k.approval_status})" for k in variants) + "."
            )
        return GovernanceAnswer(
            status="ANSWERED", question_kind="KPI_DEFINITION", headline=headline, explanation=explanation, kpis=rows,
            total_matching=len(rows), rules=[{"rule_id": "RULE-002", "rule_name": "Canonical KPI first"}],
            source={"table": "kpi_catalog"},
        )

    def _kpi_conflicts(self, prompt: str, db: Session) -> GovernanceAnswer:
        status_filter = None
        if re.search(r"\bconflict", prompt, re.IGNORECASE):
            status_filter = ["definition_conflict"]
        elif re.search(r"\bduplicate", prompt, re.IGNORECASE):
            status_filter = ["duplicate_candidate"]
        elif re.search(r"\blocal\s+variants?\b", prompt, re.IGNORECASE):
            status_filter = ["local_variant"]
        query = db.query(KpiCatalog)
        if status_filter:
            query = query.filter(KpiCatalog.definition_status.in_(status_filter))
        else:
            query = query.filter(KpiCatalog.definition_status != "canonical")
        domain = re.search(r"\b(commercial|supply\s+chain|finance|market\s+access|launch\s+excellence|bi\s+governance)\b", prompt, re.IGNORECASE)
        rows = [
            {"kpi_id": k.kpi_id, "kpi_name": k.kpi_name, "domain": k.domain, "definition_status": k.definition_status,
             "approval_status": k.approval_status, "unit": k.unit}
            for k in query.order_by(KpiCatalog.kpi_id).all()
            if not domain or k.domain.lower() == " ".join(domain.group(1).lower().split())
        ]
        label = ", ".join(status_filter) if status_filter else "non-canonical"
        return GovernanceAnswer(
            status="ANSWERED" if rows else "NO_MATCH", question_kind="KPI_CONFLICTS",
            headline=f"{len(rows)} KPI(s) in the catalog are {label}{f' in {domain.group(1)}' if domain else ''}.",
            explanation=[RULE_CONSEQUENCE["RULE-002"]], kpis=rows, total_matching=len(rows),
            rules=[{"rule_id": "RULE-002", "rule_name": "Canonical KPI first"}], source={"table": "kpi_catalog", "definition_status": status_filter or "!= canonical"},
        )

    def _ai_readiness(self, filters, db, rules) -> GovernanceAnswer:
        query = db.query(SemanticModels).filter(SemanticModels.ai_readiness != "good")
        if filters["products"]:
            query = query.filter(SemanticModels.product_scope.in_(filters["products"]))
        rows = [
            {"model_id": m.model_id, "model_name": m.model_name, "product_scope": m.product_scope, "region_scope": m.region_scope,
             "ai_readiness": m.ai_readiness, "ai_issue_pattern": m.ai_issue_pattern, "endorsement": m.endorsement}
            for m in query.order_by(SemanticModels.model_id).all()
        ]
        poor = sum(1 for r in rows if r["ai_readiness"] == "poor")
        scope = "/".join(filters["products"]) or "estate-wide"
        return GovernanceAnswer(
            status="ANSWERED" if rows else "NO_MATCH", question_kind="AI_READINESS",
            headline=f"{len(rows)} {scope} semantic model(s) are not AI-ready: {poor} poor and {len(rows) - poor} partial.",
            explanation=[f"RULE-007 ({rules.get('RULE-007', '')}): {RULE_CONSEQUENCE['RULE-007']}",
                         "Readiness comes from Semantic_Models.ai_readiness; 'good' models are excluded."],
            assets=rows[:MAX_LISTED], total_matching=len(rows), rules=[{"rule_id": "RULE-007", "rule_name": rules.get("RULE-007", "")}],
            filters=filters, source={"table": "semantic_models", "ai_readiness": ["poor", "partial"]},
        )

    def _model_refresh(self, filters, db) -> GovernanceAnswer:
        query = db.query(SemanticModels).filter(SemanticModels.refresh_status == "failed")
        if filters["products"]:
            query = query.filter(SemanticModels.product_scope.in_(filters["products"]))
        rows = [{"model_id": m.model_id, "model_name": m.model_name, "product_scope": m.product_scope, "refresh_status": m.refresh_status,
                 "refresh_frequency": m.refresh_frequency} for m in query.order_by(SemanticModels.model_id).all()]
        return GovernanceAnswer(
            status="ANSWERED" if rows else "NO_MATCH", question_kind="MODEL_REFRESH",
            headline=f"{len(rows)} semantic model(s){' for ' + '/'.join(filters['products']) if filters['products'] else ''} have a failed refresh.",
            assets=rows[:MAX_LISTED], total_matching=len(rows), filters=filters, source={"table": "semantic_models", "refresh_status": "failed"},
        )

    def _certified(self, prompt, filters, db) -> GovernanceAnswer:
        level = "promoted" if re.search(r"\bpromoted\b", prompt, re.IGNORECASE) else "certified"
        assets = [a for a in db.query(AnalyticsAssets).filter(AnalyticsAssets.endorsement == level).order_by(AnalyticsAssets.asset_id).all()
                  if self._asset_matches(a, filters)]
        owners = {o.owner_id: o for o in db.query(Owners).all()}
        rows = [self._asset_row(a, owners.get(a.owner_id)) for a in assets]
        active = sum(1 for a in assets if a.lifecycle_status == "active")
        scope = self._scope_words(filters) or "estate-wide"
        return GovernanceAnswer(
            status="ANSWERED" if rows else "NO_MATCH", question_kind="CERTIFIED",
            headline=f"{len(rows)} {scope} asset(s) are {level}; {active} of them are active.",
            explanation=["Endorsement comes from Analytics_Assets.endorsement. Non-active endorsed assets need owner confirmation before reuse."],
            assets=rows[:MAX_LISTED], total_matching=len(rows), filters=filters, source={"table": "analytics_assets", "endorsement": level},
        )

    def _summary(self, filters, db, rules) -> GovernanceAnswer:
        assets = {a.asset_id: a for a in db.query(AnalyticsAssets).all() if self._asset_matches(a, filters)}
        findings = (
            db.query(GovernanceFindings)
            .filter(GovernanceFindings.status.in_(ACTIVE), GovernanceFindings.target_entity_id.in_(list(assets) or [""]))
            .all()
        )
        by_rule: Dict[Tuple[str, str], int] = {}
        for f in findings:
            by_rule[(f.rule_id, f.severity)] = by_rule.get((f.rule_id, f.severity), 0) + 1
        critical = [f for f in findings if f.severity == "critical"]
        scope = self._scope_words(filters) or "estate-wide"
        summary = "; ".join(f"{rule} {sev}: {n}" for (rule, sev), n in sorted(by_rule.items(), key=lambda kv: (kv[0][0], _severity_key(kv[0][1]))))
        return GovernanceAnswer(
            status="ANSWERED" if findings else "NO_MATCH",
            question_kind="GOVERNANCE_SUMMARY",
            headline=(
                f"{len(assets)} {scope} asset(s) carry {len(findings)} active governance finding(s), {len(critical)} of them critical"
                + (f" (on {', '.join(sorted({f.target_entity_id for f in critical})[:8])})." if critical else ".")
            ),
            explanation=[f"By rule and severity: {summary}." if summary else "No active findings."],
            rules=[{"rule_id": r, "rule_name": n} for r, n in sorted(rules.items())],
            findings=[
                FindingView(rule_id=f.rule_id, severity=f.severity.upper(), asset_id=f.target_entity_id, kind="BLOCKER",
                            effect="PREVENTS_ACTION", message=f.title, required_action=f.recommended_action or "", finding_ids=[f.finding_id])
                for f in sorted(critical, key=lambda f: f.target_entity_id)
            ],
            total_matching=len(findings),
            filters=filters,
            source={"table": "governance_findings", "status": list(ACTIVE)},
        )
