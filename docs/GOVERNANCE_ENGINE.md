# BIOS — Milestone 1: Deterministic Governance Intelligence Engine

## 1. Overview & Objectives

The BIOS Governance Intelligence Engine evaluates the enterprise BI estate against the eight governance rules defined in the official synthetic challenge data pack. It is designed to be:
- **100% Deterministic & Explainable**: Pure mathematical/relational rules, 0 black-box hallucinations.
- **Evidence-Backed**: Every finding contains a verified primary source reference and corroborating references citing source tables, record keys, and observed values.
- **Lifecycle-Aware**: Tracks findings across evaluation runs through deterministic hash keys (`open` $\rightarrow$ `persisting` $\rightarrow$ `resolved`).
- **Audit-Ready & Human-Gated**: High and critical findings require human approval (`human_approval_required = True`) before executing consequential lifecycle transitions (retire, consolidate, migrate).

---

## 2. Architecture & Directory Structure

```
backend/app/governance/
├── __init__.py               # Public API exports
├── schemas.py                # Pydantic schemas (RuleId, FindingSeverity, FindingStatus, EvidenceBundle)
├── evidence.py               # Deterministic finding ID computation & evidence bundle factories
├── registry.py               # Central rule registration & introspection singleton
├── engine.py                 # GovernanceEngine execution orchestrator & lifecycle manager
└── rules/
    ├── __init__.py           # Rule registry packaging
    ├── base.py               # Abstract BaseGovernanceRule
    ├── rule_001_reuse.py     # RULE-001: Reuse before build
    ├── rule_002_kpi.py       # RULE-002: Canonical KPI first
    ├── rule_003_owner.py     # RULE-003: Owner required
    ├── rule_004_lineage.py   # RULE-004: Lineage required
    ├── rule_005_high_reach.py # RULE-005: High reach requires trust
    ├── rule_006_migration_waste.py # RULE-006: Do not migrate waste
    ├── rule_007_ai_readiness.py    # RULE-007: AI-ready semantics
    └── rule_008_explainability.py  # RULE-008: Explain every lifecycle action
```

---

## 3. The Eight Official Rules Implementation

| Rule ID | Rule Name | Category | Priority | Official Criteria & Thresholds | Total Findings |
|---|---|---|---|---|---|
| **RULE-001** | Reuse before build | `waste_reduction` | High | Prohibits duplicate report titles (40 duplicate names across 84 assets) and flags inbound requests when certified assets already serve the product/market context. | **159** |
| **RULE-002** | Canonical KPI first | `semantic_governance` | High | Flags unapproved/draft/conflicted KPIs (38 non-canonical KPIs) and assets mapped to non-canonical metrics. Critical severity for high-criticality KPIs. | **387** |
| **RULE-003** | Owner required | `accountability` | High | Flags 21 unowned assets (`owner_id IS NULL`, Critical), 65 assets with inactive owners (High), and 18 semantic models with inactive owners. | **104** |
| **RULE-004** | Lineage required | `lineage_integrity` | High | Flags orphan semantic models (`SM-009` with 0 lineage edges) and 15 migration candidates where unmitigated downstream assets depend on them. | **16** |
| **RULE-005** | High reach requires trust | `trust_endorsement` | Medium | Flags assets with `estimated_audience >= 500` lacking endorsement (`endorsement == 'none'`) and self-service assets with `audience >= 250`. | **180** |
| **RULE-006** | Do not migrate waste | `migration_rationalisation` | High | Flags 34 migration candidates marked `RETIRE` (22) or `CONSOLIDATE_BEFORE_MIGRATION` (12) to prevent wasteful 1:1 migration. | **34** |
| **RULE-007** | AI-ready semantics | `agentic_readiness` | Medium | Flags 45 models with poor/partial AI readiness, 48 models with naming/date/measure flaw patterns, and 33 models with failed/warning refresh status. | **69** |
| **RULE-008** | Explain every lifecycle action | `lifecycle_auditability` | High | Enforces 4-pillar evidence bundles (Metadata, Usage, Lineage, KPIs) for 156 high-usage assets queued for retirement or lifecycle review. | **156** |
| **Total** | | | | **Estate-Wide Governance Findings** | **1,105** |

---

## 4. Findings Lifecycle State Machine

1. **Deterministic Finding ID**:
   $$\text{ID} = \text{"FND-" } + \text{RuleId} + \text{"-"} + \text{SHA256}(\text{rule\_id} : \text{entity\_type} : \text{entity\_id} : \text{category})[:12]$$
2. **State Transitions**:
   - $\text{New Violation} \longrightarrow \mathbf{OPEN}$
   - $\text{Violation Persists Across Runs} \longrightarrow \mathbf{PERSISTING}$
   - $\text{Violation Remediated in Source Data} \longrightarrow \mathbf{RESOLVED} \quad (\text{resolved\_at} = \text{now})$
   - $\text{Human Exception / Acknowledgement} \longrightarrow \mathbf{ACKNOWLEDGED}$

---

## 5. API Endpoints

All endpoints are versioned under `/api/v1/governance`:

- `POST /api/v1/governance/evaluate` — Executes full evaluation across all 8 rules; persists run summary and findings.
- `GET /api/v1/governance/findings` — Lists findings with pagination (`limit`, `offset`) and filtering (`rule_id`, `severity`, `status`, `target_entity_type`, `target_entity_id`, `run_id`).
- `GET /api/v1/governance/findings/{finding_id}` — Retrieves finding by deterministic ID.
- `GET /api/v1/governance/summary` — Real-time aggregate telemetry across active/resolved findings, severities, and rules.
- `GET /api/v1/governance/rules` — Metadata and operational criteria for all 8 rules.
- `GET /api/v1/governance/rules/{rule_id}` — Detailed specifications and thresholds for a single rule.

---

## 6. Test Suite & Verification

The test suite contains **44 automated tests** executed via `backend\.venv\Scripts\python.exe -m pytest backend/tests`:
- `test_governance_rules.py` (9 tests): Validates each rule's output against the synthetic challenge dataset.
- `test_governance_engine.py` (5 tests): Validates run execution, deterministic IDs, lifecycle state transitions (`open` $\rightarrow$ `persisting` $\rightarrow$ `resolved`), single rule runs, and summary aggregation.
- `test_api_governance.py` (6 tests): Validates all HTTP endpoints, parameter validation, and 404 handlers.
- Backward compatibility: All 24 existing Milestone 0 catalog, ingestion, and model tests pass 100%.

