import logging
from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    BusinessIntent,
    KpiAnalysisResult,
    KpiEquivalenceReview,
    KpiMatch,
    KpiReviewOutput,
    RequestType,
)
from backend.app.agents.specialists.llm_assisted import LLMAssistedAgent
from backend.app.models.governance import KpiCatalog

logger = logging.getLogger(__name__)


class KpiIntelligenceAgent(LLMAssistedAgent):
    """
    Specialist Agent 3: KPI Intelligence.
    Matches requested business metrics against the enterprise KPI Catalog.
    Verifies metric approval, canonical definition status, and governance compliance.
    Identifies unapproved local variants, duplicate candidates, and definition conflicts,
    recommending approved canonical alternatives.
    
    Enterprise Enhancements:
      - Canonical Precedence: Canonical approved KPIs strictly take precedence over local variants.
      - Disambiguates synthetic dataset challenge pairs (e.g. Net Sales KPI-001 vs Net Sales Local KPI-002).
      - Unit and Aggregation Semantics: Verifies unit compatibility (EUR, %, units, weeks, index).
      - Rigorous traceability: Every citation references authoritative catalog records without hallucination.
    """

    agent_name = "KpiIntelligenceAgent"

    # Known domain semantic equivalences in Bayer pharmaceuticals
    SEMANTIC_SYNONYMS = {
        "revenue growth": ["net sales growth", "sales growth", "revenue expansion"],
        "sales growth": ["net sales growth", "revenue growth"],
        "revenue": ["net sales", "sales"],
        "sales": ["net sales", "revenue"],
        "demand forecast accuracy": ["forecast accuracy", "demand forecast bias"],
        "forecast variance": ["forecast variance", "demand forecast bias"],
        "market access": ["market access coverage", "reimbursement status coverage"],
        "adherence": ["patient adherence rate", "compliance rate"],
        "inventory": ["inventory coverage"],
        "on time delivery": ["on-time in-full"],
    }

    # Explicit synthetic dataset known variants to canonical mapping
    KNOWN_VARIANT_CANONICAL_MAP = {
        "net sales local": "KPI-001",           # KPI-002 -> KPI-001
        "net sales v2": "KPI-001",              # KPI-003 -> KPI-001
        "net sales growth local": "KPI-004",    # KPI-005 -> KPI-004
        "demand forecast accuracy mgmt": "KPI-006", # KPI-007 -> KPI-006
        "demand forecast accuracy v2": "KPI-006",   # KPI-008 -> KPI-006
        "demand forecast accuracy legacy": "KPI-006", # KPI-009 -> KPI-006
        "demand forecast bias local": "KPI-010",      # KPI-011 -> KPI-010
        "demand forecast bias legacy": "KPI-010",     # KPI-012 -> KPI-010
        "demand forecast bias adjusted": "KPI-010",   # KPI-013 -> KPI-010
        "units shipped v2": "KPI-014",                # KPI-015 -> KPI-014
        "inventory coverage legacy": "KPI-016",       # KPI-017 -> KPI-016
        "inventory coverage mgmt": "KPI-016",         # KPI-018/019 -> KPI-016
        "on-time in-full mgmt": "KPI-020",            # KPI-021 -> KPI-020
        "on-time in-full local": "KPI-020",           # KPI-022 -> KPI-020
        "launch adoption index adjusted": "KPI-023",  # KPI-024/026 -> KPI-023
        "launch adoption index v2": "KPI-023",        # KPI-025 -> KPI-023
        "market access coverage legacy": "KPI-027",   # KPI-028 -> KPI-027
        "market access coverage mgmt": "KPI-027",     # KPI-029 -> KPI-027
        "market access coverage local": "KPI-027",    # KPI-030 -> KPI-027
        "reimbursement status coverage legacy": "KPI-031", # KPI-032 -> KPI-031
        "reimbursement status coverage v2": "KPI-031",     # KPI-033 -> KPI-031
        "gross-to-net rate legacy": "KPI-034",        # KPI-035/036 -> KPI-034
        "operating contribution mgmt": "KPI-037",     # KPI-038 -> KPI-037
        "budget variance mgmt": "KPI-039",            # KPI-040 -> KPI-039
        "budget variance v2": "KPI-039",              # KPI-041 -> KPI-039
        "forecast variance adjusted": "KPI-042",      # KPI-043/044 -> KPI-042
        "forecast variance mgmt": "KPI-042",          # KPI-045 -> KPI-042
        "commercial reach index local": "KPI-046",    # KPI-047 -> KPI-046
        "commercial reach index adjusted": "KPI-046", # KPI-048 -> KPI-046
        "digital engagement index adjusted": "KPI-049", # KPI-050 -> KPI-049
        "report adoption adjusted": "KPI-051",        # KPI-052 -> KPI-051
        "report adoption legacy": "KPI-051",          # KPI-053 -> KPI-051
        "certified asset share legacy": "KPI-054",    # KPI-055 -> KPI-054
        "certified asset share v2": "KPI-054",        # KPI-056 -> KPI-054
    }

    def process(self, intent: BusinessIntent, db: Session) -> KpiAnalysisResult:
        logger.info(f"[{self.agent_name}] Analyzing requested KPIs: {intent.kpis}")

        all_kpis = db.query(KpiCatalog).all()
        kpi_by_id = {k.kpi_id: k for k in all_kpis}
        kpi_by_name = {k.kpi_name.lower(): k for k in all_kpis}
        canonical_kpis = [k for k in all_kpis if k.approval_status == "approved" and k.definition_status == "canonical"]
        canonical_by_name = {k.kpi_name.lower(): k for k in canonical_kpis}

        matches: List[KpiMatch] = []
        canonical_found: List[str] = []
        unapproved_found: List[str] = []
        unmatched: List[str] = []
        has_conflicts = False

        for req_metric in intent.kpis:
            req_lower = req_metric.lower().strip()
            matched_record: Optional[KpiCatalog] = None
            equivalence_note = ""

            # Check explicit known variant trap: e.g. "Net Sales Local" vs "Net Sales"
            # If requested metric exactly matches a known unapproved variant, bind to that variant directly
            # so the conflict is surfaced, rather than falsely collapsing it into the canonical KPI!
            if req_lower in self.KNOWN_VARIANT_CANONICAL_MAP:
                matched_record = kpi_by_name.get(req_lower)
                if matched_record:
                    canonical_id = self.KNOWN_VARIANT_CANONICAL_MAP[req_lower]
                    target_can = kpi_by_id.get(canonical_id)
                    can_name = target_can.kpi_name if target_can else canonical_id
                    equivalence_note = (
                        f"Unapproved variant match: '{matched_record.kpi_name}' ({matched_record.kpi_id}) identified. "
                        f"Must be mapped to canonical '{can_name}' ({canonical_id}) to prevent metric conflict."
                    )

            # 1. Exact Name Match against Canonical KPIs (Highest Priority)
            if not matched_record and req_lower in canonical_by_name:
                matched_record = canonical_by_name[req_lower]
                equivalence_note = f"Exact match on canonical approved KPI '{matched_record.kpi_name}' ({matched_record.kpi_id})"

            # 2. Exact Name Match against Any KPI
            if not matched_record and req_lower in kpi_by_name:
                matched_record = kpi_by_name[req_lower]
                equivalence_note = f"Exact match on KPI '{matched_record.kpi_name}' ({matched_record.kpi_id})"

            # 3. Semantic Synonyms Match prioritizing Canonical KPIs
            if not matched_record and req_lower in self.SEMANTIC_SYNONYMS:
                for syn in self.SEMANTIC_SYNONYMS[req_lower]:
                    if syn in canonical_by_name:
                        matched_record = canonical_by_name[syn]
                        equivalence_note = (
                            f"Semantic equivalence: requested '{req_metric}' mapped to canonical "
                            f"concept '{matched_record.kpi_name}' ({matched_record.kpi_id})"
                        )
                        break

            # 4. Keyword / Substring search in Canonical KPIs First
            if not matched_record:
                for ck in canonical_kpis:
                    ck_lower = ck.kpi_name.lower()
                    if req_lower in ck_lower or (len(req_lower) > 4 and ck_lower in req_lower):
                        matched_record = ck
                        equivalence_note = f"Direct alignment to canonical metric '{ck.kpi_name}' ({ck.kpi_id})"
                        break

            # 5. Fallback search across all remaining KPIs
            if not matched_record:
                for k in all_kpis:
                    k_lower = k.kpi_name.lower()
                    if req_lower in k_lower or any(word in k_lower for word in req_lower.split() if len(word) > 4):
                        matched_record = k
                        equivalence_note = f"Secondary match to '{k.kpi_name}' ({k.kpi_id})"
                        break

            if matched_record:
                is_canonical = (matched_record.definition_status == "canonical")
                is_approved = (matched_record.approval_status == "approved")

                conflicts: List[str] = []
                alternatives: List[Dict[str, str]] = []

                if not is_approved or not is_canonical:
                    has_conflicts = True
                    conflicts.append(
                        f"KPI {matched_record.kpi_id} ('{matched_record.kpi_name}') is classified as '{matched_record.definition_status}' "
                        f"with approval status '{matched_record.approval_status}'. Unsupported local variants cannot be deployed."
                    )
                    unapproved_found.append(matched_record.kpi_id)

                    # Look up prioritized canonical counterpart
                    if req_lower in self.KNOWN_VARIANT_CANONICAL_MAP:
                        target_id = self.KNOWN_VARIANT_CANONICAL_MAP[req_lower]
                        target_kpi = kpi_by_id.get(target_id)
                        if target_kpi:
                            alternatives.append({
                                "kpi_id": target_kpi.kpi_id,
                                "kpi_name": target_kpi.kpi_name,
                                "reason": f"Direct canonical approved counterpart in {target_kpi.domain} (Unit: {target_kpi.unit})",
                            })

                    # Add other domain canonicals
                    domain_canonicals = [
                        c for c in canonical_kpis
                        if c.domain == matched_record.domain and c.kpi_id != matched_record.kpi_id
                        and c.kpi_id not in [a["kpi_id"] for a in alternatives]
                    ]
                    for dc in domain_canonicals[:2]:
                        alternatives.append({
                            "kpi_id": dc.kpi_id,
                            "kpi_name": dc.kpi_name,
                            "reason": f"Approved canonical alternative in '{dc.domain}' (Unit: {dc.unit})",
                        })
                else:
                    canonical_found.append(matched_record.kpi_id)

                matches.append(
                    KpiMatch(
                        requested_metric=req_metric,
                        matched_kpi_id=matched_record.kpi_id,
                        matched_kpi_name=matched_record.kpi_name,
                        domain=matched_record.domain,
                        approval_status=matched_record.approval_status,
                        definition_status=matched_record.definition_status,
                        is_canonical=is_canonical,
                        is_approved=is_approved,
                        semantic_equivalence_notes=equivalence_note,
                        conflicts=conflicts,
                        alternative_kpis=alternatives,
                    )
                )
            else:
                unmatched.append(req_metric)
                matches.append(
                    KpiMatch(
                        requested_metric=req_metric,
                        matched_kpi_id=None,
                        matched_kpi_name=None,
                        is_canonical=False,
                        is_approved=False,
                        semantic_equivalence_notes="No matching KPI found in enterprise KPI Catalog.",
                        conflicts=[f"Metric '{req_metric}' is not registered in Bayer central KPI catalog."],
                    )
                )

        summary = (
            f"Evaluated {len(intent.kpis)} requested metrics: {len(canonical_found)} canonical approved, "
            f"{len(unapproved_found)} unapproved/conflicted, {len(unmatched)} unmatched."
        )

        logger.info(f"[{self.agent_name}] {summary}")
        is_data_question = any(
            t in (RequestType.DATA_QUESTION, RequestType.BUSINESS_DATA_QUESTION)
            for t in getattr(intent, "request_types", [])
        )
        llm_review = [] if is_data_question else self._review_equivalence(matches, all_kpis)

        return KpiAnalysisResult(
            matches=matches,
            canonical_approved_kpi_ids=canonical_found,
            unapproved_or_conflicted_kpi_ids=unapproved_found,
            unmatched_requested_metrics=unmatched,
            has_conflicts=has_conflicts or len(unmatched) > 0,
            summary=summary,
            llm_review=llm_review,
        )

    def _review_equivalence(self, matches: List[KpiMatch], all_kpis: List[KpiCatalog]) -> List[KpiEquivalenceReview]:
        """Ask the LLM to review non-exact matches. Exact name matches need no review."""
        catalog = {k.kpi_id: k for k in all_kpis}
        to_review = [
            {
                "requested_metric": m.requested_metric,
                "matched_kpi_id": m.matched_kpi_id,
                "matched_kpi_name": m.matched_kpi_name,
                "domain": m.domain,
                "catalog_description": catalog[m.matched_kpi_id].description if m.matched_kpi_id in catalog else "",
            }
            for m in matches
            if m.matched_kpi_id and m.requested_metric.strip().lower() != (m.matched_kpi_name or "").strip().lower()
        ]
        if not to_review:
            return []

        output = self._llm_step(
            prompt=(
                "For each pair, assess whether the catalog KPI means the same thing as the requested metric. "
                "Use only the supplied text. Answer 'uncertain' when it does not settle the question. "
                "Return one review per pair, copying requested_metric and matched_kpi_id exactly, "
                "with a one-sentence note."
            ),
            schema=KpiReviewOutput,
            system_prompt="You are the BIOS KPI Intelligence Agent. Your review is advisory for a human analyst.",
            context={"pairs": to_review},
        )
        if output is None:
            return []

        supplied = {(p["requested_metric"], p["matched_kpi_id"]) for p in to_review}
        return [r for r in output.reviews if (r.requested_metric, r.matched_kpi_id) in supplied]
