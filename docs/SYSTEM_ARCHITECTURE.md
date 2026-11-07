# System Architecture

## Style
Modular monolith. Keep explicit module boundaries; do not split into microservices during the hackathon.

## Layers
1. Experience: assistant, command centre, asset explorer, governance console, artifact studio, admin.
2. API/identity: FastAPI, authentication boundary, role checks, validation.
3. Intelligence: intent, semantic discovery, evidence fusion, recommendation orchestration.
4. Governance: deterministic rules, scoring, duplicate candidates, lifecycle constraints.
5. Artifact Factory: DashboardSpec, templates, generation adapters, automated checks.
6. Asset lifecycle: registry, ownership, versions, publication, lineage, verification.
7. Integrations: Power BI first, n8n and optional UNO Q.

## Main flow
Request → structured intent → discovery → evidence bundle → deterministic governance → lifecycle recommendation → (if justified) DashboardSpec → validation → human approval → Power BI export/publish path → asset registry → verification.

## Deployment
Local Windows development; cloud-ready configuration. PostgreSQL locally or managed dev instance. n8n is an external workflow integration, not the business-rules engine. Arduino is optional.

## Failure boundaries
LLM unavailable: retain deterministic discovery/governance and manual path where possible. n8n unavailable: core app continues. Arduino unavailable: no core impact. Power BI unavailable: retain validated preview/export-pending state; never claim publication succeeded.
