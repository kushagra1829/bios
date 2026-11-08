# BIOS Role & Permission Matrix

**Classification:** Enterprise Security Architecture Specification  
**Version:** 1.0.0  
**Scope:** BIOS (Business Intelligence Optimization System)  
**Security Model:** Deny-by-Default, Hierarchical Scope & Role-Based Access Control (RBAC)

---

## 1. Executive Summary

BIOS enforces fine-grained, role-based workspace visibility, API authorization barriers, and query-level organizational data scoping. Navigation elements rendered on the frontend are purely ergonomic affordances; **the backend authorization layer constitutes the non-bypassable security boundary**. Direct URL navigation or REST API calls violating role entitlements immediately terminate with HTTP `403 Forbidden`.

The platform strictly differentiates five enterprise operational roles:
1. **`REQUESTER` / `ANALYST`**: Individual business contributor submitting analytics demand, inspecting catalog metadata in read-only mode, and monitoring self-originated approval requests.
2. **`ASSET_OWNER`**: Analytics developer and product owner responsible for assigned assets, reviewing remediation findings on owned reports, and adjudicating incoming change requests targeting owned models.
3. **`DOMAIN_STEWARD`**: Regional and therapeutic domain leader governing semantic consistency, cross-asset consolidation, KPI standardization, and domain-wide Power BI / DAX model generation.
4. **`BI_GOVERNANCE_REVIEWER`**: Enterprise-level governance lead reviewing fleet-wide compliance, executing 8 deterministic governance evaluations, adjudicating waivers, and inspecting continuous drift monitoring. Strictly partitioned from system infrastructure.
5. **`BIOS_ADMIN`**: Platform and systems administrator possessing exclusive authority over platform configuration, diagnostic services, secret management, and external BI connector configurations (Power BI & Tableau Service Principals).

---

## 2. Workspace Navigation Matrix

The table below defines the visibility of top-level workspaces across the sidebar navigation and UI routing.

| Workspace | Route Path | REQUESTER | ASSET_OWNER | DOMAIN_STEWARD | BI_GOVERNANCE_REVIEWER | BIOS_ADMIN |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **Command Center** | `/dashboard` | Allowed (Tailored) | Allowed (Tailored) | Allowed (Tailored) | Allowed (Tailored) | Allowed (Full) |
| **Analytics Intelligence** | `/assistant` | Allowed (6-Agent) | Allowed (6-Agent) | Allowed (6-Agent) | Allowed (6-Agent) | Allowed (6-Agent) |
| **Analytics Portfolio** | `/assets` | Read-Only | Scoped (Owned) | Scoped (Domain) | Full Fleet (360 Assets) | Full Fleet (360 Assets) |
| **Governance & Compliance** | `/governance` | **Denied (403)** | Allowed (Scoped) | Allowed (Domain) | Allowed (Full Evaluation) | Allowed (Full Evaluation) |
| **Alert Centre** | `/alerts` | **Denied (403)** | Allowed (Scoped) | Allowed (Domain) | Allowed (Enterprise) | Allowed (Enterprise) |
| **Approvals & Decisions** | `/approvals` | Allowed (Own Only) | Allowed (Target Assets) | Allowed (Domain Scope) | Allowed (Enterprise) | Allowed (Override) |
| **Lifecycle Management** | `/lifecycle` | **Denied (403)** | Allowed (Owned Assets) | Allowed (Domain Scope) | Allowed (Enterprise) | Allowed (Enterprise) |
| **Development Studio** | `/artifacts` | **Denied (403)** | **Denied (403)** | Allowed (Domain Scope) | Allowed (Enterprise) | Allowed (Enterprise) |
| **Continuous Monitoring**| `/monitoring`| **Denied (403)** | **Denied (403)** | **Denied (403)** | Allowed (Enterprise) | Allowed (Enterprise) |
| **Platform Admin** | `/admin` | **Denied (403)** | **Denied (403)** | **Denied (403)** | **Denied (403)** | Allowed |
| **BI Integrations** | `/integrations` | **Denied (403)** | **Denied (403)** | **Denied (403)** | **Denied (403)** | Allowed |

*Note: The `/integrations` workspace is completely hidden from the standard sidebar for non-administrative clarity, and is accessible only to `BIOS_ADMIN` with explicit backend credential access.*

---

## 3. Backend REST API Resource Permission Matrix

Every incoming API request is resolved against `backend.app.auth.dependencies.get_current_user` and gated by deterministic permission dependencies (`require_role`, `require_admin`).

| Resource Group | Endpoint Route | HTTP Method | Minimum Required Role | Query Data Scoping Applied |
|---|---|:---:|---|---|
| **Command Center Telemetry** | `/api/v1/dashboard/telemetry` | `GET` | `REQUESTER` | Tailored JSON payload matching actor role & database boundaries |
| **Analytics Catalog** | `/api/v1/catalog/assets` | `GET` | `REQUESTER` | Unrestricted read-only catalog; supports `?owner_id=` and `?scoped=` |
| **Catalog Detail** | `/api/v1/catalog/assets/{id}` | `GET` | `REQUESTER` | Public metadata read-only |
| **AI Assistant** | `/api/v1/assistant/chat` | `POST` | `REQUESTER` | All six agents execute; requests tagged with actor ID & role |
| **Governance Findings** | `/api/v1/governance/findings` | `GET` | `ASSET_OWNER` | `ASSET_OWNER` receives findings restricted to assigned asset IDs |
| **Governance Evaluation** | `/api/v1/governance/evaluate` | `POST` | `BI_GOVERNANCE_REVIEWER` | Full fleet evaluation blocked for Requesters, Owners & Stewards |
| **Active Alerts** | `/api/v1/alerts/active` | `GET` | `ASSET_OWNER` | Filtered by `target_entity_id IN (assigned_asset_ids)` for Owners |
| **Alert Acknowledgment** | `/api/v1/alerts/{id}/ack` | `POST` | `ASSET_OWNER` | Requires ownership of target entity; minimum 5-char rationale |
| **List Approvals** | `/api/v1/approvals` | `GET` | `REQUESTER` | Requesters: `requester_id == actor_id`; Owners: target owned assets |
| **Approval Detail** | `/api/v1/approvals/{id}` | `GET` | `REQUESTER` | Requesters blocked (403) from accessing foreign approval tickets |
| **Adjudicate Approval** | `/api/v1/approvals/{id}/approve` | `POST` | `ASSET_OWNER` | Blocked (403) for Requesters; blocked if adjudicator == requester |
| **Reject Approval** | `/api/v1/approvals/{id}/reject` | `POST` | `ASSET_OWNER` | Blocked (403) for Requesters |
| **Lifecycle Fleet** | `/api/v1/lifecycle/assets` | `GET` | `ASSET_OWNER` | Blocked (403) for Requesters; delivers health & migration scores |
| **Lifecycle Transition** | `/api/v1/lifecycle/transition` | `POST` | `ASSET_OWNER` | Requires asset ownership or domain governance authority |
| **Artifact Generation** | `/api/v1/artifacts/generate` | `POST` | `DOMAIN_STEWARD` | Blocked (403) for Requesters and Asset Owners |
| **Artifact Detail** | `/api/v1/artifacts/{id}` | `GET` | `DOMAIN_STEWARD` | Blocked (403) for Requesters and Asset Owners |
| **Continuous Monitoring**| `/api/v1/monitoring/health` | `GET` | `BI_GOVERNANCE_REVIEWER` | Blocked (403) for Requesters, Asset Owners, and Stewards |
| **BI Connectors** | `/api/v1/integrations` | `GET` | `BIOS_ADMIN` | Blocked (403) for all 4 non-admin roles |
| **Connector Diagnostics**| `/api/v1/integrations/{id}/test`| `POST` | `BIOS_ADMIN` | Blocked (403) for all 4 non-admin roles |

---

## 4. Query-Level Data Scoping Rules

Authorization does not stop at HTTP route rejection; queries returning collection sets enforce strict database-level WHERE clauses:

### 4.1 Requester / Analyst Scope
- **Approvals**: Query scoped to `requester_id == user.actor_id`. Requesters never receive approval tickets submitted by other users.
- **Approval Detail**: If an approval ticket does not belong to the Requester and the Requester is not an approver, `HTTP 403 Forbidden: Requesters can only access their own approval tickets` is returned.
- **Adjudication**: Requesters attempting to POST approve or reject actions receive `HTTP 403 Forbidden: Requesters cannot adjudicate approvals`.

### 4.2 Asset Owner Scope
- **Assigned Assets**: Extracted dynamically from `backend.app.models.core.AnalyticsAssets` where `owner_id == user.actor_id` or `business_owner == user.actor_name`.
- **Findings & Alerts**: Queries automatically append `filter(GovernanceFinding.asset_id.in_(user.assigned_asset_ids))` or `filter(Alert.target_entity_id.in_(user.assigned_asset_ids))`.
- **Approvals**: Receives requests where `target_entity_id IN (user.assigned_asset_ids)`.

### 4.3 Domain Steward Scope
- **Assigned Domains**: Resolved from `Owners.scope` or organizational affiliation (e.g. `Commercial Analytics`, `Finance BI`).
- **Development Studio**: Can compile and generate Power BI PBIP/PBIR semantic models, DAX measures, and metadata artifacts within domain scope.

### 4.4 BI Governance Reviewer Scope
- **Enterprise Fleet**: Full visibility over all 360 catalog assets, 8 governance rules, active waivers, and continuous drift monitoring.
- **Administrative Boundary**: Strictly barred from system-level platform administration, configuration mutations, and integration credential access.

---

## 5. Anti-Bypass & Defense-in-Depth

1. **Header Resolution**: Authentication context is extracted from `X-Actor-Id` and `X-Actor-Role` headers passed securely across corporate reverse proxies or frontend session states.
2. **Database Owner Validation**: If an actor ID matches an entity in the `Owners` table, the user's active status is verified. Inactive owners are immediately denied (`HTTP 403 Forbidden: Inactive owners cannot perform operations`).
3. **Anti-Self-Approval Safeguard**: The system prohibits users from approving their own change or waiver requests, regardless of their role rank.
4. **Deny-by-Default Fallback**: Any route or resource without explicit role enablement defaults to strict denial.

