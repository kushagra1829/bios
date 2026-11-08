# BIOS — Milestone 5.7: Next.js Frontend Command Center & Integration Report

> [!NOTE]
> **Scope Refinement Notice (Milestone 5.7.2)**:
> Section 7 (Arduino Edge Companion Terminal) and the `/arduino` route documented below have been superseded and removed from the active BIOS platform scope.
> BIOS operates exclusively as an 8-page, software-based enterprise application.

**Report Date:** 2026-11-07  
**Milestone:** 5.7 — Next.js Frontend Command Center & Full Backend Integration  
**Baseline Git Commit:** `99c8fd01632e4e4a0cc1646f9d7338a8d7e06aab`  
**Dataset SHA-256:** `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab`  
**Application URLs:**
- Frontend Web UI: `http://localhost:3000`
- Backend REST API: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

---

## 1. Executive Summary

Milestone 5.7 successfully delivers the enterprise Next.js Command Center for BIOS (**Business Intelligence Optimization System**). It transforms the backend intelligence platform into an interactive, highly responsive software operating system for enterprise analytics governance.

Zero mock data is used where real APIs exist. Every core operational view connects directly to FastAPI backend services, enforces deterministic governance rules, visualizes sequential multi-agent orchestration traces, exercises live human approval workflows with backend-enforced RBAC (including Milestone 5.6 N4 and N5 controls), and displays Power BI artifact specifications with verified structural packaging.

---

## 2. Core Navigation Areas & Page Architecture

The frontend application is structured into 9 dedicated pages with persistent global navigation, header status telemetry, and active role-switching controls:

| # | Route | Page Title | Primary Backend Integration | Key Features |
|---|---|---|---|---|
| **1** | `/dashboard` | Executive Command Center | `GET /api/v1/governance/estate/summary`<br>`GET /api/v1/approvals/summary`<br>`GET /api/v1/migration/summary` | Estate KPIs, portfolio governance score (87.4%), 8 deterministic rules breakdown, interactive quick-action cards |
| **2** | `/assistant` | Multi-Agent AI Assistant | `POST /api/v1/assistant/request`<br>`GET /api/v1/assistant/requests/{id}` | 5 clickable scenario prompts, live 6-agent sequential execution traces, intent extraction, duplicate detection, governed recommendations |
| **3** | `/assets` | Analytics Asset Explorer | `GET /api/v1/catalog/assets`<br>`GET /api/v1/catalog/assets/{id}` | Searchable catalog (Tableau & Power BI), platform & endorsement filters, view counts, detailed metadata drawer |
| **3b** | `/assets/[assetId]` | Asset Detail & Lineage | `GET /api/v1/catalog/assets/{id}`<br>`GET /api/v1/governance/findings` | Owner assignment, health metrics, semantic model mapping, active governance findings, upstream lineage |
| **4** | `/governance` | Governance Console | `GET /api/v1/governance/rules`<br>`GET /api/v1/governance/findings`<br>`POST /api/v1/governance/evaluate` | All 8 deterministic rules, severity badges, live evaluation scan trigger, active findings inspector |
| **5** | `/approvals` | Approval Center | `GET /api/v1/approvals`<br>`POST /api/v1/approvals/{id}/approve`<br>`POST /api/v1/approvals/{id}/reject`<br>`POST /api/v1/approvals/{id}/request-changes` | Status filtering (PENDING/APPROVED/REJECTED), interactive decision modal with mandatory rationale, N4 live owner & N5 waiver validation error feedback |
| **6** | `/lifecycle` | Estate Rationalization & Migration | `GET /api/v1/migration/summary`<br>`GET /api/v1/migration/recommendations` | 94 Tableau backlog candidates, action filtering (`MIGRATE`, `CONSOLIDATE`, `RETIRE`), complexity badges, rationalization rationale |
| **7** | `/artifacts` | Power BI Artifact Studio | `GET /api/v1/artifacts`<br>`GET /api/v1/artifacts/{id}`<br>`GET /api/v1/artifacts/{id}/files`<br>`POST /api/v1/artifacts/generate` | Power BI Developer Project (.pbip + PBIR) generation, TMDL measure inspector, G0–G3 PASS and G4 UNVERIFIED verification ladder |
| **8** | `/arduino` | Arduino Edge Companion | `GET /api/v1/arduino/status` (M6 Contract) | Truthfully displayed as `HARDWARE INTEGRATION PENDING` / `NOT CONNECTED`, HMAC-SHA256 contract spec, physical safety interlock preview |
| **9** | `/admin` | Administration & Diagnostics | `GET /health`<br>`GET /api/v1/governance/rules`<br>`GET /api/v1/audit/events` | Real backend health, SQLite WAL mode, Alembic revision (`b4f1c2d7e8a9`), Local Ollama (Qwen 3.5 4B), official dataset SHA-256, immutable audit trail |

---

## 3. Visual Identity & Design System

The Command Center implements an enterprise-grade dark-on-light theme grounded in the project design tokens:

- **Midnight Navy (`#142438`)**: Primary brand, navigation sidebar, card headings, and data terminal containers.
- **Intelligence Blue (`#3478F6`)**: Primary interactive buttons, active links, agent badge indicators, and primary KPI callouts.
- **Trust Green (`#16A085`)**: Endorsed assets, passing governance rules, approved requests, and G0–G3 verification tags.
- **Warning Amber (`#E5A12B`)**: Pending approvals, consolidation recommendations, warnings, and hardware pending pill.
- **Critical Red (`#DC5252`)**: Severe governance violations, immediate retirement paths, and rejected requests.
- **Cloud Gray (`#F2F5F9`)**: Workspace application canvas, subtly textured borders, and accessible card surfaces.

---

## 4. Multi-Agent Assistant Interaction & 6-Agent Traces

The Assistant view (`/assistant`) demonstrates the full multi-agent lifecycle across all 6 specialized agents:
1. **Request Intake Agent**: Normalizes user prompt and classifies business domain.
2. **Intent Parser Agent**: Extracts target products, markets, KPIs, and temporal scope.
3. **Analytics Discovery Agent**: Scans existing assets for exact or partial matches.
4. **Duplicate Intelligence Agent**: Computes structural and semantic similarity scores.
5. **Governance Validator Agent**: Verifies compliance against 8 deterministic rules.
6. **Recommendation Synthesis Agent**: Generates governed decision (`REUSE`, `CONSOLIDATE`, `RETIRE`, `MODIFY`, or `BUILD_NEW`).

Users can test all 5 core business scenarios via one-click prompt pills:
- **Scenario 1 (Direct Reuse)**: Cardiology Reach Analysis $\to$ Exact reuse recommendation for `AST-0001`.
- **Scenario 2 (Duplicate Block)**: Oncology Brand Performance $\to$ Identifies existing high-similarity asset, blocks duplicate.
- **Scenario 3 (Orphaned / Unowned)**: Market Access $\to$ Flags unowned asset, routes to steward for ownership remediation.
- **Scenario 4 (Non-Canonical KPI)**: Custom Reach metric $\to$ Flags non-standard formula, recommends canonical KPI.
- **Scenario 5 (Tableau Modernization)**: Legacy Tableau report $\to$ Recommends governed migration to shared Power BI semantic model.

Each response expands to reveal the sequential execution trace for all 6 agents with latency breakdown, model name (`qwen2.5:3.5b` or deterministic regex), execution mode, and structured step inputs/outputs.

---

## 5. Security & RBAC Enforcement (N4 & N5 Controls)

The Header incorporates a live Role & Actor Switcher (`OWN-001`, `OWN-019`, `steward_sarah`, `reviewer_george`, `auditor_alex`, `requester_rachel`) allowing direct evaluation of backend access controls:

- **Anti-Self-Approval Ban**: Requesters cannot approve their own requests; attempting to do so triggers a `403 Forbidden` response surfaced in the UI.
- **Live Owner Authority Verification (N4)**: Asset owners are checked against the live SQLite `Owners` database table. Inactive owners (13 in dataset) are prevented from reviewing requests, with immediate error feedback.
- **Synchronous Waiver Expiry (N5)**: Approved waivers checked dynamically against current server timestamps; expired waivers cannot be used to bypass the reuse gate.

---

## 6. Power BI Artifact Studio & Verification Ladder

The Artifact Studio (`/artifacts`) provides complete transparency regarding Power BI project generation:
- **G0 (Schema Syntax)**: Valid JSON / TMDL structure $\to$ **PASS**
- **G1 (Folder Hierarchy)**: Standard `.pbip` report and dataset layout $\to$ **PASS**
- **G2 (Semantic Integrity)**: Measures, tables, and relationships generated $\to$ **PASS**
- **G3 (Packaging)**: Multi-file PBIR definition files generated $\to$ **PASS**
- **G4 (Desktop Engine)**: Desktop rendering and UI validation $\to$ **UNVERIFIED (Truthfully indicated pending Power BI Desktop host installation)**

---

## 7. Arduino Edge Companion Terminal

The `/arduino` route serves as the companion terminal for Milestone 6 physical telemetry:
- Status banner prominently displays `HARDWARE INTEGRATION PENDING` / `NOT CONNECTED`.
- Zero fake mock telemetry: strictly truthful status.
- Full contract specification displayed: polling intervals (5000ms), endpoint schemas (`/api/v1/arduino/status`), HMAC-SHA256 signature requirements, and the non-authoritative boundary guarantee.

---

## 8. Verification Results

### 8.1 Next.js Production Build
```
Route (app)                              Size     First Load JS
┌ ○ /                                    138 B          87.5 kB
├ ○ /_not-found                          873 B          88.2 kB
├ ○ /admin                               5.72 kB          93 kB
├ ○ /approvals                           3.44 kB         106 kB
├ ○ /arduino                             3.92 kB        91.2 kB
├ ○ /artifacts                           4.18 kB         106 kB
├ ○ /assets                              3.34 kB         101 kB
├ ƒ /assets/[assetId]                    3.59 kB         101 kB
├ ○ /assistant                           4.13 kB         106 kB
├ ○ /dashboard                           5.59 kB         103 kB
├ ○ /governance                          4 kB            101 kB
└ ○ /lifecycle                           4.02 kB         101 kB
+ First Load JS shared by all            87.3 kB

Exit Code: 0 (Zero errors, zero warnings)
```

### 8.2 Backend Automated Test Suite
- Total Tests Collected: **410**
- Tests Passed: **396**
- Tests Skipped: **14** (Local Ollama live tests when offline)
- Tests Failed: **0**
- Benchmark & Reliability Tests (`backend/tests/test_reliability_n4_n5.py` + `backend/tests/benchmarks`): **43/43 Passed**

### 8.3 Synthetic Dataset Integrity
- File: `data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx`
- SHA-256 Digest: `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab` (Verified identical)

