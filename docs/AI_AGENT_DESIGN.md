# AI Design

Start with specialist services, not a swarm of autonomous agents:
- Intent: extract purpose, domain, metrics, dimensions, filters, time range and ambiguity.
- Discovery: retrieve candidate assets, models and KPIs.
- Evidence: assemble provenance-backed evidence and identify gaps.
- Decision: propose lifecycle options using deterministic metrics and policy results.
- Artifact: propose a DashboardSpec referencing approved KPIs, fields and templates.

All model calls use one provider adapter configured by environment. Use Pydantic schemas for BusinessIntent, EvidenceBundle, LifecycleRecommendation, DashboardSpec and ValidationReport.

LLMs may interpret, map, summarise and propose. Deterministic code calculates metrics, enforces policy and validates. Expose uncertainty. Record model/prompt/schema versions where useful. Require human approval for consequential actions.
