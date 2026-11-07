# BIOS — Business Intelligence Optimization System

BIOS helps enterprises turn business questions into fewer, better, maintainable and governed analytics products.

## Two connected engines
1. **Analytics Optimization Engine:** discover, evaluate, reuse, consolidate, repair, migrate or retire existing analytics.
2. **Analytics Artifact Factory:** create new analytics only when existing assets cannot satisfy the request.

## Locked architecture
- Local Windows development; cloud-ready deployment later.
- Google Antigravity workspace; Claude Code primary implementation agent; Gemini reviewer.
- Next.js + TypeScript + Tailwind CSS + shadcn/ui.
- Python + FastAPI modular monolith.
- PostgreSQL; pgvector when semantic retrieval is justified.
- Pandas; Pydantic; deterministic Python governance rules.
- Provider-independent AI adapter with configurable Gemini/Claude provider.
- Power BI first; n8n for optional workflows; UNO Q optional.
- GitHub as source of truth.

## Repository
`frontend/` UI · `backend/` API and domain logic · `data/` local datasets · `docs/` specifications · `workflows/` n8n · `hardware/` UNO Q · `tests/` tests.

## Implementation rules
- Reuse before build.
- Never invent KPI definitions, source fields, owners or lineage.
- Preserve source data and provenance.
- AI proposes; deterministic rules validate; authorised humans approve consequential actions.
- Every recommendation explains evidence, uncertainty and next steps.
- Generated artifacts must be reproducible from versioned specifications and controlled templates.
- Core BIOS must work if an LLM provider, n8n or Arduino is unavailable.

This is an architecture scaffold, not a running application yet.
