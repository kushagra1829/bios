# BIOS Milestone 5.10 — Frontend Architecture & Enterprise UX Specification

**Version:** 5.10.0  
**Status:** Approved & Validated  
**Author:** Principal Enterprise Product Designer & Senior Next.js Architect  
**Dataset Digest:** `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab`  
**Application Scope:** Software-only Enterprise Business Intelligence Optimization System  

---

## 1. Executive Architecture Summary

Milestone 5.10 completes the end-to-end transformation of BIOS from an engineering milestone prototype into an enterprise-grade Analytics Governance & Optimization platform. The user interface directly reflects the core philosophy: **"Build less. Build better. Govern intelligently."**

The frontend is built on **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, and **Recharts**, interfacing via typed contracts with the **FastAPI** backend and its 6-agent deterministic governance pipeline.

---

## 2. Route & Module Hierarchy

```
frontend/app/
├── layout.tsx                   # Enterprise shell, font providers, global banner
├── page.tsx                     # Landing & workspace redirection router
├── not-found.tsx                # Enterprise 404 handler (governed fallback)
├── dashboard/
│   └── page.tsx                 # Module 1: Enterprise Intelligence Command Center
├── assistant/
│   └── page.tsx                 # Module 2: Enterprise Analytics Intelligence (6-Agent)
├── assets/
│   ├── page.tsx                 # Module 3: Analytics Portfolio Explorer (360 assets)
│   └── [assetId]/
│       └── page.tsx             # Module 3b: Governed Asset Deep-Dive & Lineage
├── governance/
│   └── page.tsx                 # Module 4: Governance & Compliance Center (8 rules)
├── approvals/
│   └── page.tsx                 # Module 5: Human Approvals & Decision Center
├── lifecycle/
│   └── page.tsx                 # Module 6: Estate Rationalization & Migration Backlog
├── artifacts/
│   └── page.tsx                 # Module 7: Governed Analytics Development Studio
└── admin/
    └── page.tsx                 # Module 8: Platform Administration & Provenance
```

> **Non-Negotiable Scope Guard:** The legacy `/arduino` hardware edge route is completely eliminated. Requests to `/arduino` return a governed `404 Not Found` response.

---

## 3. Design System & Visual Token Foundation

### 3.1 Color Palette & Semantic Assignment
The UI enforces strict color hierarchy to convey operational meaning:

- **Executive & Neutral Structure:** `midnight-900` (`#0f172a`), `slate-800` (`#1e293b`), `gray-50` (`#f8fafc`).
- **Intelligence & Agent Activity:** `intelligence` (`#2563eb` / `#1d4ed8`), with indigo accents (`#4f46e5`).
- **Governance & Compliance Integrity:** `emerald-600` / `emerald-700` (`PASS` / Certified / Healthy).
- **Adjudication & Human Decisions:** `amber-600` / `amber-700` (Pending Review / Warning).
- **Rule Enforcement & Blockers:** `rose-600` / `rose-700` (Critical Violations / Blockers / Retirement).

### 3.2 Typography & Density
- Inter-based typography scale (`text-xs` to `text-2xl`) tailored for dense information display.
- Tabular data renders with `tabular-nums` and monospace styling for IDs (`AST-xxxx`, `RULE-xxx`, `SM-xxx`).
- Visual density preserves whitespace without sacrificing high information throughput necessary for portfolio oversight.

---

## 4. Multi-Turn Session Lifecycle in AI Assistant

The AI Assistant (`/assistant`) implements a session-scoped multi-turn memory architecture:

1. **State Isolation:** Session conversations are retained in memory per browser session (`ConversationTurn[]`), tracking user inquiries, backend execution timestamps, agent trace steps, and final decision objects.
2. **Interactive Clarification Loop:** When the 6-agent orchestrator yields `NEEDS_CLARIFICATION`, the UI exposes an interactive clarification form. Submitting an answer merges the user's supplemental intent with the preceding context without fabricating persistent session records on the backend.
3. **Trace Visualization:** All 6 agent steps (`IntentAgent`, `DiscoveryAgent`, `KpiIntelligenceAgent`, `DuplicationAgent`, `GovernanceAgent`, `DecisionAgent`) display in a structured execution timeline with duration, latency, execution mode, and collapsible raw input/output payloads.
4. **Export & Auditability:** Analysts can copy structured markdown decision briefs or download the complete machine-readable JSON recommendation packet with a single click.

---

## 5. Live Backend Integration & Error Resilience

All UI components interact with the FastAPI backend through `frontend/lib/api.ts`:

- **Defensive Number Formatting:** All metric calculations and percentage displays route through `frontend/lib/format.ts` (`formatPercent`, `formatMs`, `formatNumber`), strictly preventing `TypeError: Cannot read properties of undefined (reading 'toFixed')`.
- **Envelope Unwrapping:** Paginated backend collections (`/api/v1/assets`, `/api/v1/kpis`, `/api/v1/semantic-models`) containing `{ items: [...], meta: {...} }` are cleanly unwrapped to ensure predictable array mappings.
- **Fail-Safe Offline Mode:** If the backend becomes temporarily unreachable, components render contextual retry cards with actionable diagnostics rather than throwing unhandled client-side exceptions.

---

## 6. Governed Adjudication & Security Guardrails

The Approvals Center (`/approvals`) enforces enterprise authorization invariants:

- **Role Attribution:** Adjudications require valid actor identity and designated governance role (`BI Governance Reviewer`, `Asset Owner`, `Platform Administrator`).
- **Mandatory Rationale:** Approvals, rejections, and change requests require a documented business justification ($\ge 5$ characters).
- **Authoritative Enforcement:** Approval actions trigger synchronous backend API calls with state reflection and instant queue recalculation.

