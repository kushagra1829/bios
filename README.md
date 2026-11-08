# BIOS — Business Intelligence Optimization System

> **Enterprise BI Governance, Multi-Agent Analytics Optimization & Governed Artifact Provisioning**

BIOS is an enterprise-grade platform designed to optimize and govern enterprise business intelligence estates. It transforms incoming business and reporting requests into governed analytics actions: reusing existing certified assets, consolidating redundant reports, enforcing canonical KPI definitions, and automating compliant Power BI project generation.

---

## Key Capabilities

1. **Enterprise Role-Aware Workspaces**
   - True backend authorization and scoped data access tailored for 5 organizational roles:
     - **Requester / Analyst**: Submit business questions, discover permitted assets, and track personal approval requests.
     - **Asset Owner**: Custody over assigned assets, adjudicate inbound modification/reuse requests, and monitor asset health.
     - **Domain Steward**: Oversee domain-level reporting standards, canonical KPI consistency, and semantic model certification.
     - **BI Governance Reviewer**: Global governance oversight, 8 deterministic compliance rules, and artifact factory access.
     - **BIOS Administrator**: Platform diagnostics, system health telemetry, and service integration management.

2. **Deterministic Multi-Agent AI Analytics Engine**
   - Six specialized cooperating agents: **Intent**, **Discovery**, **Duplication**, **KPI**, **Governance**, and **Decision**.
   - Dual-intent classification distinguishes pure **Business Data Questions** (direct metric calculation from monthly data packs) from **Analytics Asset Requests** (catalog lookups and reuse recommendations).
   - Grounded strictly in factual data—zero invented metrics, owners, or lineage.

3. **Database-Backed Approvals & Human Adjudication**
   - Complete approval workflow lifecycle with persistent state transitions (`PENDING`, `APPROVED`, `REJECTED`, `CHANGES_REQUESTED`).
   - Integrated N4, N5, and N6 safeguards: strict custody checks, blocker overrides, anti-self-approval restrictions, and full audit event logging.
   - Real-time cross-workspace synchronization: requests submitted by Requesters route instantly to the appropriate Asset Owner's queue without manual data refresh.

4. **Power BI Artifact Factory (`PBIP` / `PBIR`)**
   - Automatically generates version-controlled Power BI project structures (`.pbip`), TMDL semantic models, and PBIR report definitions.
   - Comprehensive multi-tier validation:
     - **G0–G3 Verified**: Structural syntax, JSON schema compliance, and DAX metric validation.
     - **G4 Validation Ready**: Transparent status tracking prior to target Power BI Desktop / Fabric Tenant publication.

---

## System Architecture

BIOS is architected as a modular monolith:

```
BIOS-starter/
├── backend/                  # FastAPI Application Core
│   ├── app/
│   │   ├── agents/           # 6-Agent Multi-Agent Orchestration & Answering Engine
│   │   ├── analytics/        # Synthetic Data Pack Ingestion & Query Execution
│   │   ├── api/v1/           # REST Endpoints (Approvals, Catalog, Governance, Lifecycle, etc.)
│   │   ├── approvals/        # Approval Workflow Engine, Routing & State Transitions
│   │   ├── artifacts/        # Power BI (.pbip) Artifact Factory & TMDL Generator
│   │   ├── auth/             # Role-Based Access Control (RBAC) & Actor Scoping
│   │   ├── db/               # SQLAlchemy Models & SQLite (WAL Mode) Session
│   │   ├── governance/       # Deterministic Rule Engine & Hallucination Guardrails
│   │   └── integrations/     # BI Connectors (Power BI, Tableau) & Webhooks
│   └── tests/                # Comprehensive Pytest Regression & Integration Test Suites
├── frontend/                 # Next.js 14 (App Router) + TypeScript + Tailwind CSS
│   ├── app/                  # Enterprise Workspaces (Dashboard, Approvals, Assistant, Assets, etc.)
│   ├── components/           # Role-Aware Navigation, Shell, Modals & Visualizations
│   ├── lib/                  # API Client, Role Permissions & TypeScript Contracts
│   └── tests/                # Frontend RBAC & Route Barrier Test Suites
├── data/                     # Source Data & Local SQLite Storage
│   ├── source/               # Approved Synthetic Challenge Data Pack (.xlsx)
│   ├── exports/              # Generated Power BI Projects (.pbip)
│   └── bios.db               # SQLite Database (WAL Mode Enabled)
├── docs/                     # Architecture Specifications, Benchmarks & QA Audits
└── AGENTS.md                 # Developer Contract & Strict Implementation Invariants
```

---

## Quickstart Guide

### Prerequisites
- **Python**: Version 3.11+ (Tested on Python 3.14 on Windows)
- **Node.js**: Version 18+ (Tested on Node.js 24)

### 1. Backend Setup & Startup

From the project root:

```powershell
# 1. Create and activate Python virtual environment
py -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 2. Configure environment
Copy-Item .env.example .env

# 3. Apply database migrations
backend\.venv\Scripts\python.exe -m alembic upgrade head

# 4. Start the FastAPI server
backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The interactive API documentation is accessible at: <http://127.0.0.1:8000/docs>

### 2. Frontend Setup & Startup

In a separate terminal:

```powershell
# 1. Navigate to frontend directory and install dependencies
cd frontend
npm install

# 2. Start the development server (or run 'npm run build' && 'npm start' for production)
npm run dev
```

The BIOS Command Center interface is accessible at: <http://localhost:3000>

### 3. Ingestion & Estate Baseline Initialization

From a third terminal, seed the catalog, evaluate governance rules, and populate lifecycle status:

```powershell
# Run synthetic dataset ingestion
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/ingestion/run

# Evaluate 8 deterministic governance rules across all 360 assets
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/governance/evaluate

# Evaluate estate migration & modernization candidates
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lifecycle/evaluate
```

---

## Role-Based Workspaces & Personas

Switch roles seamlessly via the enterprise workspace selector in the top-right header:

| Role Name | Persona ID | Primary Scope & Access | Visible Workspaces |
| :--- | :--- | :--- | :--- |
| **Requester / Analyst** | `REQ-001` | Self-Service Analytics & Tracking | Command Center, AI Intelligence, Portfolio, Approvals (Own Requests) |
| **Asset Owner** | `OWN-001` (Nina Garcia) | Owned Asset Custody (Cardiology / Nubeqa) | Command Center, AI Intelligence, Portfolio, Governance, Alerts, Approvals, Lifecycle |
| **Domain Steward** | `OWN-004` (Elena Rostova) | Commercial Domain Governance | All above + Analytics Development Studio (Artifacts) |
| **BI Governance Reviewer** | `REV-001` (Dr. Aris Thorne) | Global Governance Oversight | All above + Continuous Monitoring |
| **BIOS Administrator** | `ADM-001` (Sarah Jenkins) | Full Infrastructure & Configuration | All 10 workspaces including Platform Administration |

---

## Testing & Quality Assurance

BIOS includes comprehensive automated test suites covering backend RBAC, multi-agent intent routing, approval workflows, and frontend navigation barriers.

### Running Backend Tests
```powershell
# Run cross-workspace approval workflow tests
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_cross_workspace_approval_workflow.py -v

# Run new request submission & routing tests
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_new_approval_submission.py -v

# Run full backend test suite
backend\.venv\Scripts\python.exe -m pytest backend/tests/ -q
```

### Running Frontend Tests
```powershell
# Validate 100% route barriers and role-based navigation scoping
node frontend/tests/role_navigation.test.mjs
```

---

## Governance, Scope & Data Disclaimer

- **Software-Only Architecture**: BIOS is an exclusively software-based enterprise platform. Hardware integrations (e.g. Arduino companions) are completely removed from project scope. Optional n8n workflow integration remains available.
- **Dataset Provenance**: BIOS uses the synthetic challenge dataset `data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx`, approved explicitly for SinceAI challenge evaluation. It contains no real patient records or confidential internal corporate data.
- **Human-in-the-Loop Safeguards**: AI agents propose; deterministic business rules validate; authorized human owners adjudicate consequential decisions.
