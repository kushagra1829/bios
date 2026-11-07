# Analytics Artifact Factory

## Pipeline
Intent → approved evidence and KPI selection → versioned DashboardSpec → approved template/components → deterministic generation → automated validation → preview/human review → supported BI export/publication → asset registration.

DashboardSpec describes purpose, domain, audience, canonical KPI IDs, approved source/model references, dimensions, filters, grain, visual bindings, layout tokens, access classification, owner and approver requirements.

Validate schema, KPI references, field references, grain/relationships, calculation mapping, owner metadata, lineage, access classification, design tokens and target-tool compatibility.

## Repeatability demo
Run two different requests through the same specification schema, templates and validator. Introduce an invalid KPI/field reference and show publication is blocked.

## Power BI caution
A .pbip extension/folder alone does not prove a functional report. Validate the generation route in Power BI tooling and document exactly what is implemented.
