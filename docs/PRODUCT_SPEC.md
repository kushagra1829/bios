# Product Specification

## Problem and promise
Enterprise self-service BI can create dashboard sprawl, duplicate logic, inconsistent KPIs, unclear ownership and technical debt. BIOS helps enterprises turn business questions into fewer, better, maintainable and governed analytics products.

## Product modes
### Optimize existing analytics
Discover reports, dashboards, semantic models and KPIs; evaluate overlap, usage, ownership, lineage, freshness and governance; recommend reuse, consolidate, repair, migrate, retire or review.

### Create new analytics
Clarify request; discover canonical KPIs and approved sources; create a versioned DashboardSpec; generate from controlled templates; validate; preview; obtain approval; register the artifact.

## Users
Business requester/consumer, business owner, technical owner, data steward, BI/platform administrator, governance administrator and approver. Roles can be combined, responsibilities should remain explicit.

## Domain strategy
Domain-independent engine; domain-specific business context, terminology, KPI catalogue, permissions and templates. Support Pharma, Crop Science, Consumer Health and functions such as R&D, Marketing, Logistics, Quality, Finance, IT, Legal and Compliance. Do not hardcode manufacturing assumptions.

## MVP
- Import synthetic builder pack.
- Natural-language request and structured intent.
- Asset/KPI discovery and evidence-backed recommendation.
- Deterministic implementation of the eight supplied governance rules.
- Human review and approval.
- Power BI-oriented artifact generation/integration path with honest limitations.
- Asset registry, ownership, version and lifecycle metadata.
- Repeatable artifact specification and automated validation.

## Principles
Reuse before build; evidence before recommendation; canonical KPI first; ownership and lineage matter; AI proposes, rules validate, humans approve; verify outcomes; artifacts must be reproducible; integrate with BI platforms rather than create another isolated BI ecosystem.
