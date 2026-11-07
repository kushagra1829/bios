import logging
from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    BusinessIntent,
    KpiAnalysisResult,
    KpiEquivalenceReview,
    KpiMatch,
    KpiReviewOutput,
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

    Catalog matching and approval checks are deterministic. The LLM reviews non-exact
    matches and flags doubtful equivalences as advice in llm_review; it cannot change a
    KPI ID, approval status or conflict flag.
    """

    agent_name = "KpiIntelligenceAgent"

    # Known domain semantic equivalences in Bayer pharmaceuticals
    SEMANTIC_SYNONYMS = {
        "revenue growth": ["net sales growth", "sales growth", "revenue expansion"],
        "sales growth": ["net sales growth", "revenue growth"],
        "revenue": ["net sales", "sales", "gross sales"],
        "sales": ["net sales", "revenue"],
        "forecast variance": ["demand forecast accuracy", "demand forecast bias", "forecast accuracy"],
        "market access": ["market access coverage", "reimbursement status coverage"],
        "adherence": ["patient adherence rate", "compliance rate"],
    }

    def process(self, intent: BusinessIntent, db: Session) -> KpiAnalysisResult:
        logger.info(f"[{self.agent_name}] Analyzing requested KPIs: {intent.kpis}")

        all_kpis = db.query(KpiCatalog).all()
        kpi_by_name = {k.kpi_name.lower(): k for k in all_kpis}
        canonical_kpis = [k for k in all_kpis if k.approval_status == "approved" and k.definition_status == "canonical"]

        matches: List[KpiMatch] = []
        canonical_found: List[str] = []
        unapproved_found: List[str] = []
        unmatched: List[str] = []
        has_conflicts = False

        for req_metric in intent.kpis:
            req_lower = req_metric.lower().strip()
            matched_record: Optional[KpiCatalog] = None
            equivalence_note = ""

            # 1. Exact Name Match
            if req_lower in kpi_by_name:
                matched_record = kpi_by_name[req_lower]
                equivalence_note = f"Exact match on KPI name '{matched_record.kpi_name}'"

            # 2. Semantic Synonyms Match
            if not matched_record and req_lower in self.SEMANTIC_SYNONYMS:
                for syn in self.SEMANTIC_SYNONYMS[req_lower]:
                    if syn in kpi_by_name:
                        matched_record = kpi_by_name[syn]
                        equivalence_note = f"Semantic equivalence: requested '{req_metric}' mapped to canonical concept '{matched_record.kpi_name}'"
                        break

            # 3. Substring / Keyword Search in Canonical KPIs first
            if not matched_record:
                for ck in canonical_kpis:
                    ck_lower = ck.kpi_name.lower()
                    if req_lower in ck_lower or any(word in ck_lower for word in req_lower.split() if len(word) > 3):
                        matched_record = ck
                        equivalence_note = f"Keyword alignment to canonical metric '{ck.kpi_name}' in domain '{ck.domain}'"
                        break

            # 4. Fallback search across all KPIs
            if not matched_record:
                for k in all_kpis:
                    k_lower = k.kpi_name.lower()
                    if req_lower in k_lower or any(word in k_lower for word in req_lower.split() if len(word) > 3):
                        matched_record = k
                        equivalence_note = f"Fuzzy match to '{k.kpi_name}'"
                        break

            if matched_record:
                is_canonical = (matched_record.definition_status == "canonical")
                is_approved = (matched_record.approval_status == "approved")

                conflicts: List[str] = []
                alternatives: List[Dict[str, str]] = []

                if not is_approved or not is_canonical:
                    has_conflicts = True
                    conflicts.append(
                        f"KPI {matched_record.kpi_id} is '{matched_record.definition_status}' "
                        f"with approval status '{matched_record.approval_status}'."
                    )
                    unapproved_found.append(matched_record.kpi_id)

                    # Find approved canonical alternative in same domain
                    domain_canonicals = [
                        c for c in canonical_kpis
                        if c.domain == matched_record.domain and c.kpi_id != matched_record.kpi_id
                    ]
                    for dc in domain_canonicals[:2]:
                        alternatives.append({
                            "kpi_id": dc.kpi_id,
                            "kpi_name": dc.kpi_name,
                            "reason": f"Approved canonical alternative in '{dc.domain}'",
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
                        conflicts=[f"Metric '{req_metric}' is not registered in Bayer KPI catalog."],
                    )
                )

        summary = (
            f"Evaluated {len(intent.kpis)} requested metrics: {len(canonical_found)} canonical approved, "
            f"{len(unapproved_found)} unapproved/conflicted, {len(unmatched)} unmatched."
        )

        logger.info(f"[{self.agent_name}] {summary}")
        return KpiAnalysisResult(
            matches=matches,
            canonical_approved_kpi_ids=canonical_found,
            unapproved_or_conflicted_kpi_ids=unapproved_found,
            unmatched_requested_metrics=unmatched,
            has_conflicts=has_conflicts or len(unmatched) > 0,
            summary=summary,
            llm_review=self._review_equivalence(matches, all_kpis),
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
                "catalog_description": catalog[m.matched_kpi_id].description,
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

