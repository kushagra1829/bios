# Coding-agent contract

Read README.md and relevant docs before implementation. This repository and docs are the source of truth.

1. Work only on the assigned task; report files changed and tests run.
2. Do not silently change API contracts, database models or design tokens.
3. Keep a modular monolith; do not introduce microservices for the hackathon.
4. Use typed schemas and deterministic, independently tested business rules.
5. All LLM calls go through the provider adapter.
6. Never invent source fields, KPI definitions, owners or lineage.
7. Do not commit .env, credentials, real business data or source datasets.
   Exception: `data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx` is the synthetic SinceAI hackathon dataset, explicitly approved for public repository inclusion by the challenge representative. No other files in `data/source/` are permitted.
8. Human approval is required for consequential lifecycle actions.
9. Do not claim Power BI publication succeeded until validated in target tooling.
10. Arduino and n8n are optional integrations, never core dependencies.
11. Add tests and update docs for behaviour changes.
12. Do not overwrite another agent's uncommitted work.
