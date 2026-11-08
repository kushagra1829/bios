# BIOS — Backend API Integration Reference

**Document Version**: 1.0.0 (Milestone 5.6)  
**API Version**: v1 (`/api/v1`)  
**Base URL**: `http://localhost:8000`  
**Host Framework**: FastAPI 0.115+ (ASGI, Starlette)  
**Authentication Boundary**: Server-Authoritative RBAC & Authoritative Database Session (`data/bios.db`)  

---

## 1. Overview & Architectural Principles

The BIOS backend exposes a comprehensive, RESTful API engineered primarily for:
1. **The Next.js Command Center Frontend** (Enterprise Web UI).
2. **Programmatic API Clients & Enterprise Workflows** (Software-only governance integration; hardware/Arduino integrations removed in Milestone 5.7.2).

### Core Architectural Guarantees
- **Separation of Advisory vs. Consequential Operations**: AI Agent recommendations (`/api/v1/assistant/...`) are strictly advisory and cannot mutate production assets or grant permissions. Consequential lifecycle changes require explicit human approval via `/api/v1/approvals/...`.
- **Live Inactive-Owner Verification (N4 Control)**: Re-queries authoritative `Owners` table at execution time; stale or newly deactivated owners are rejected server-side.
- **Synchronous Expiration Enforcement (N5 Control)**: Point-of-use expiration validation; expired waivers and approvals are synchronously rejected regardless of stored database state.
- **Append-Only Immutable Audit Trail**: Consequential transitions generate immutable `AuditEvents` records with before/after state snapshots.
- **Deterministic Fallback**: If local Ollama inference is offline or in sandbox mode, all endpoints function with 100% deterministic rule and graph fidelity.

---

## 2. Global Error Handling & Standard Schemas

All error responses return structured JSON matching the RFC 7807 problem details pattern:

```json
{
  "error": "Descriptive human-readable error explanation",
  "status_code": 403,
  "details": null
}
```

### Standard HTTP Status Codes
| HTTP Status | Meaning | Typical Trigger |
|---|---|---|
| **200 OK** | Success | Query returned or state changed successfully |
| **201 Created** | Resource Created | New approval request or artifact specification persisted |
| **403 Forbidden** | Authorization Veto | Self-approval attempt, AI agent authorization, inactive owner, expired waiver, or role authority deficit |
| **404 Not Found** | Missing Entity | Entity ID does not exist in relational database |
| **422 Unprocessable** | Validation / Blocker Veto | Active governance blocker without formal waiver; invalid state machine transition; missing reason |
| **500 Internal Error** | Server Fault | Unhandled exception (isolated and logged server-side) |

---

## 3. API Surface Reference by Domain

### 3.1 System Health & Diagnostics
- `GET /health`: Returns service health status, database connection, and local Ollama status.
- `GET /`: Returns API service name, version, and documentation links.

### 3.2 Asset & Domain Catalog (`/api/v1`)
- `GET /api/v1/assets`: Paginated catalog of 360 analytics assets. Supports filtering by `platform` (Tableau/Power BI), `product_scope`, `market_scope`, and `lifecycle_status`.
- `GET /api/v1/assets/{asset_id}`: Detailed asset metadata, lineage dependencies, and active governance findings.
- `GET /api/v1/semantic-models`: Catalog of 75 semantic models, AI readiness scores, and issue patterns.
- `GET /api/v1/kpis`: Catalog of canonical and non-canonical KPIs, domain classifications, and approval status.

### 3.3 Governance Intelligence (`/api/v1/governance`)
- `GET /api/v1/governance/rules`: Lists all 8 deterministic governance rules (`RULE-001` through `RULE-008`).
- `GET /api/v1/governance/rules/{rule_id}`: Rule description, predicate definition, severity level, and remediation guidance.
- `POST /api/v1/governance/evaluate`: Triggers evaluation run across all 8 rules. Persists findings and returns execution summary.
- `GET /api/v1/governance/summary`: Active findings count grouped by severity (Critical, High, Medium, Low) and rule ID.
- `GET /api/v1/governance/findings`: Filterable findings list with evidence bundles.

### 3.4 Multi-Agent Analytics Assistant (`/api/v1/assistant`)
- `POST /api/v1/assistant/requests`: Submits natural language request (e.g. *"I need a Nubeqa sales dashboard with net sales and forecast variance"*). Executes 6-agent sequential orchestration (`IntentAgent` $\rightarrow$ `DiscoveryAgent` $\rightarrow$ `KpiAgent` $\rightarrow$ `DuplicationAgent` $\rightarrow$ `GovernanceAgent` $\rightarrow$ `DecisionAgent`).
- `GET /api/v1/assistant/requests`: Lists historical assistant requests.
- `GET /api/v1/assistant/requests/{request_id}`: Retrieves request record, parsed intent, and orchestration status.
- `GET /api/v1/assistant/requests/{request_id}/recommendation`: Synthesized decision (`REUSE`, `CONSOLIDATE`, `MODIFY`, `RETIRE`, `BUILD_NEW`, `NEEDS_CLARIFICATION`), confidence score, rationale, target assets, and required approvals.
- `GET /api/v1/assistant/requests/{request_id}/traces`: Sequential audit traces for each specialist agent step (execution duration, model used, structured handoff).

### 3.5 Lifecycle & Migration Intelligence (`/api/v1/lifecycle` & `/api/v1/migration`)
- `POST /api/v1/lifecycle/evaluate`: Scores all 360 assets across 7 weighted lifecycle dimensions.
- `GET /api/v1/lifecycle/assets/{asset_id}`: Detailed lifecycle assessment, utilization decay, and recommended action.
- `GET /api/v1/migration/candidates`: Rationalized Tableau migration backlog (94 assets) with complexity scores and target model mappings.
- `GET /api/v1/migration/summary`: High-level migration metrics (Retire vs. Consolidate vs. Migrate breakdown).

### 3.6 Human Approval Workflows (`/api/v1/approvals`)
- `GET /api/v1/approvals`: Filterable list of approval requests (`status`, `required_role`, `target_entity_type`).
- `POST /api/v1/approvals`: Submits new approval request with evidence snapshot.
- `GET /api/v1/approvals/{approval_id}`: Detailed approval request view with blockers and warnings.
- `POST /api/v1/approvals/{approval_id}/approve`: Authorizes request.
  - **Enforcement**: Verifies RBAC, anti-self-approval, live active owner status (N4), synchronous waiver expiry (N5), and hard governance blockers.
- `POST /api/v1/approvals/{approval_id}/reject`: Rejects request with mandatory substantive justification.
- `POST /api/v1/approvals/{approval_id}/request-changes`: Returns request to requester for modification.
- `GET /api/v1/approvals/{approval_id}/history`: Immutable chronological state transition history.
- `GET /api/v1/approvals/queue/summary`: Queue metrics (pending, approved, rejected, expired).

### 3.7 Immutable Audit Trail (`/api/v1/audit`)
- `GET /api/v1/audit/events`: Filterable, append-only audit log entries with before/after state snapshots.
- `GET /api/v1/audit/events/{event_id}`: Specific event detail, actor identity, action type, and provenance hash.

### 3.8 Power BI Artifact Factory (`/api/v1/artifacts`)
- `POST /api/v1/artifacts/specs`: Validates and saves dashboard specification.
- `GET /api/v1/artifacts/specs/{spec_id}`: Retrieves dashboard specification.
- `POST /api/v1/artifacts/generate`: Generates Power BI project artifact (`.pbip`, TMDL model, PBIR report).
  - **Enforcement**: Blocks new build requests if decision was `REUSE`/`CONSOLIDATE`/`MODIFY` (RULE-001 Reuse Gate). Verifies approved human approval synchronously for `BUILD_NEW`.
- `GET /api/v1/artifacts/{artifact_id}`: Provenance manifest and validation report (G0–G3 status, G4 status).
- `GET /api/v1/artifacts/{artifact_id}/download`: Streams ZIP archive of generated project files.

---

## 4. Frontend & Hardware Integration Notes

1. **Authentication Mode**: For hackathon evaluation, user role and identity are passed via request payload headers (`actor_id`, `actor_role`). In production enterprise deployment, these map to authenticated OIDC/SAML claims.
2. **Deterministic Response Times**: Non-LLM endpoints execute in $<50\text{ms}$. Multi-agent assistant requests in deterministic mode execute in $<40\text{ms}$.
3. **CORS Configuration**: Enabled for `http://localhost:3000` (Next.js development server) and local peripherals.

