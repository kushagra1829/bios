# Database Schema — Logical Model

Use PostgreSQL. Add pgvector only when embedding retrieval is implemented and justified.

Initial entities: users, roles, permissions, user_roles, business_domains, analytics_assets, semantic_models, kpi_definitions, asset_kpi_mappings, data_sources, lineage_edges, asset_usage_events, refresh_events, governance_rules, governance_findings, business_requests, request_intents, evidence_items, lifecycle_recommendations, dashboard_specs, artifact_versions, approval_requests, approval_events, verification_watches, verification_results, integration_connections, audit_events.

An asset should have a stable BIOS ID, source platform and source ID, name, description, domain, business owner, technical owner, optional data steward, lifecycle, certification/approval state, sensitivity, KPI references, model/source references, lineage, version and timestamps.

Preserve source workbook identifiers and provenance. Keep imported source records distinguishable from BIOS-generated records. Use migrations; avoid destructive automatic schema changes.
