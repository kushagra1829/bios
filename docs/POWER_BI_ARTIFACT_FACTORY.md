# BIOS — Milestone 5: Power BI Artifact Factory

## 1. Executive Summary

Milestone 5 implements the **Power BI Artifact Factory** for the Business Intelligence Optimization System (BIOS). Rather than operating as a typical dashboard generator that blindly manufactures reports upon request, BIOS implements an intelligent, governance-first artifact engine that:
1. **Enforces a strict Reuse-First Gate**: Blocks generation of new dashboards when existing analytics can be reused (`REUSE`), consolidated (`CONSOLIDATE`), or modified (`MODIFY`), in strict compliance with Bayer Governance Rule **RULE-001** (Reuse First / No Duplication).
2. **Requires Human Approval for Consequential Actions**: Mandatory approved `ApprovalRequests` in state `APPROVED` for `BUILD_NEW` decisions before generation proceeds.
3. **Produces Genuine Power BI Projects (`.pbip`)**: Generates true Fabric/Power BI developer artifacts, including TMDL (`.tmdl`) semantic models with compatibility level 1567 and PBIR (`report.json`) report definitions with BIOS hybrid design system tokens (`#142438` Midnight, `#3478F6` Intelligence Blue, `#16A085` Trust Green, `#F2F5F9` Cloud).
4. **Applies Authoritative Data Integrity**: References only canonical columns from the synthetic challenge workbook's relational models (`ProductMarketMonthly`, `Products`, `Markets`, `MarketAccess`) and canonical KPIs (`KPI-001`, `KPI-004`, `KPI-027`), never inventing source fields or relationships.
5. **Multi-Stage Validation with Truthful Tooling Reporting**: Validates structural existence, JSON schemas, TMDL syntax/semantics, field/measure reference integrity, and star-schema relationships. If `PBIDesktop.exe` is absent on the host environment, BIOS truthfully reports `UNVERIFIED (PBIDesktop.exe not found on host)` and returns `VALID_WITH_UNVERIFIED_DESKTOP`, never faking a live Desktop test pass.
6. **Immutable Audit Logging**: Every generation and lifecycle action records an immutable row in `audit_events`.

---

## 2. Architecture & File Layout

```
backend/app/artifacts/
├── __init__.py               # Public exports
├── schemas.py                # Pydantic models (DashboardSpec, VisualSpec, ValidationReport, etc.)
├── template_manager.py       # Canonical Bayer schemas, KPI measures, relationships, theme tokens
├── tmdl_generator.py         # Generates .SemanticModel (database.tmdl, model.tmdl, tables/*.tmdl, relationships.tmdl)
├── pbir_generator.py         # Generates .Report (definition.pbir, definition/report.json)
├── provenance.py             # SHA-256 cryptographic provenance hashing for spec & files
├── validator.py              # Multi-stage validator (schema, TMDL, PBIR queryRef integrity, Desktop check)
├── spec_builder.py           # Programmatic builder for canonical DashboardSpecs
├── service.py                # Core orchestration, reuse-first gate, audit event generation
└── router.py                 # FastAPI endpoints mounted under /api/v1/artifacts
```

Database entities added in `backend/app/models/artifact.py` (migrated via Alembic `23e1de4c1b6b`):
- `dashboard_specifications`: Stores declarative dashboard specs, product/market scope, and business purpose.
- `generated_artifacts`: Stores artifact generation records, file paths, status (`validated`, `validation_failed`), provenance, and full validation reports.

---

## 3. Generated Power BI Project Structure (`.pbip`)

Generated projects are exported to `data/exports/powerbi/<ProjectName>_<SpecId>/`:

```
<SafeProjectName>_<SpecId>/
├── <SafeProjectName>.pbip                     # Root project pointer (version 1.0)
├── <SafeProjectName>.SemanticModel/           # TMDL Dataset definition
│   ├── definition.pbidataset                 # Dataset settings
│   └── definition/
│       ├── database.tmdl                     # compatibilityLevel: 1567
│       ├── model.tmdl                        # culture: en-US, powerBI_V3, legacyRedirects
│       ├── relationships.tmdl                # Star schema relationships
│       └── tables/                           # Per-table TMDL files
│           ├── ProductMarketMonthly.tmdl     # Columns, DAX measures, M import query
│           ├── Products.tmdl
│           ├── Markets.tmdl
│           └── MarketAccess.tmdl
└── <SafeProjectName>.Report/                  # PBIR Report definition
    ├── definition.pbir                       # datasetReference pointing to ../<SafeProjectName>.SemanticModel
    └── definition/
        └── report.json                       # Sections, visualContainers, cards, charts, theme tokens
```

---

## 4. Reuse-First Gate & Governance Integration

Under Bayer Governance Rule **RULE-001** and Milestone 2 recommendation decisions:
- If a business request evaluates to `REUSE`, `CONSOLIDATE`, or `MODIFY`, `ArtifactService.generate_artifact` blocks generation immediately with HTTP 409 Conflict:
  ```
  REUSE_GATE_VETO: Recommended action is CONSOLIDATE. Direct generation of a new dashboard 
  is prohibited under Bayer Governance Rule RULE-001. Existing analytics asset should be reused or consolidated.
  ```
- If a business request evaluates to `BUILD_NEW`, the factory requires an approved human approval request (`ApprovalRequests` with `status == "APPROVED"`). Unapproved requests are rejected with HTTP 403 Forbidden.

---

## 5. Canonical Data & KPI Mapping

All generated TMDL models and PBIR visuals reference strictly validated entities:

| Entity / KPI | Real Column / DAX Expression | Description |
|---|---|---|
| **ProductMarketMonthly** | `product_id`, `market_id`, `month`, `net_sales_m_eur_syn`, `forecast_m_eur_syn`, `units_shipped_syn`, `forecast_variance_pct`, `otif_pct_syn` | Core commercial fact table |
| **KPI-001** | `SUM('ProductMarketMonthly'[net_sales_m_eur_syn])` | Total Net Sales (M EUR) |
| **KPI-004** | `DIVIDE(SUM('ProductMarketMonthly'[net_sales_m_eur_syn]) - SUM('ProductMarketMonthly'[forecast_m_eur_syn]), SUM('ProductMarketMonthly'[forecast_m_eur_syn]), 0) * 100` | Forecast Variance % |
| **KPI-027** | `SUM('ProductMarketMonthly'[units_shipped_syn])` | Total Units Shipped |
| **Total Forecast** | `SUM('ProductMarketMonthly'[forecast_m_eur_syn])` | Total Forecast (M EUR) |

---

## 6. Multi-Stage Validation Engine

The validator executes 7 sequential checks:
1. `file_structure_pbip`: Root `.pbip` exists at root level.
2. `file_structure_semantic_model`: `.SemanticModel/` directory and required definition files exist.
3. `file_structure_report`: `.Report/` directory and required definition files exist.
4. `pbip_json_schema` & `pbir_schema`: Valid JSON syntax and dataset cross-references.
5. `tmdl_database_compatibility`: Compatibility level is set to 1567 and TMDL syntax compiles cleanly.
6. `report_reference_integrity`: Every field and measure referenced in visual `queryRef` properties exists in the table schemas or measure definitions. Invocation of non-existent fields immediately causes validation failure (`FAIL`).
7. `relationship_integrity`: Keys in star-schema relationships connect valid existing columns.
8. `desktop_smoke_verification`: Honestly inspects local host environment for `PBIDesktop.exe`. If missing, reports `UNVERIFIED (PBIDesktop.exe not found on host)` without fabricating a pass.

---

## 7. REST API Endpoints

Mounted under `/api/v1/artifacts`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/artifacts/specifications` | Create and store a new dashboard specification |
| `GET` | `/api/v1/artifacts/specifications/{id}` | Retrieve dashboard specification by ID |
| `POST` | `/api/v1/artifacts/generate` | Generate PBIP artifact project (enforces reuse gate & approvals) |
| `GET` | `/api/v1/artifacts` | List generated artifacts |
| `GET` | `/api/v1/artifacts/{id}` | Get generated artifact details |
| `POST` | `/api/v1/artifacts/{id}/validate` | Trigger on-demand revalidation of generated artifact |
| `GET` | `/api/v1/artifacts/{id}/validation` | Retrieve validation report for artifact |

---

## 8. Verification & Demonstration Results

### Automated Test Suite
- Total tests: **106 passed in 9.34s** (`pytest backend/tests`).
- Milestones 0–4 tests (92 tests): 100% passing with zero regressions.
- Milestone 5 tests (14 new tests): 100% passing (`test_artifact_spec.py`, `test_artifact_reuse_gate.py`, `test_artifact_generation.py`, `test_artifact_validator.py`, `test_artifact_api.py`).

### Demo Scenarios (`backend.scripts.demo_milestone5`)
1. **Scenario 1 (Nubeqa Commercial Request Duplicate Overlap)**:
   - Prompt: *"I need a new dashboard to track Nubeqa sales performance and market share in the US."*
   - Assistant Decision: `CONSOLIDATE` (matches candidate `AST-0090` / `AST-0065`).
   - Generation Result: **Blocked with `REUSE_GATE_VETO` under Rule RULE-001**.
2. **Scenario 2 (Novel Scope Kerendia China Launch)**:
   - Prompt: *"Build commercial performance dashboard for Kerendia launch in China with net sales, forecast variance, and unit volumes."*
   - Unapproved Attempt: Blocked by approval gate (`APPROVAL_REQUIRED`).
   - Approved Workflow: With `ApprovalRequests` approved by `BI_GOVERNANCE_REVIEWER`, project generates successfully to disk:
     - Root `.pbip` generated
     - `.SemanticModel` TMDL files generated with 4 tables and canonical DAX measures
     - `.Report` PBIR files generated with cards, line chart, bar chart, slicers, and BIOS theme tokens
     - Validation Status: `VALID_WITH_UNVERIFIED_DESKTOP` (all structural and reference checks `PASS`, Desktop truthfully marked `UNVERIFIED`)
     - Cryptographic SHA-256 provenance and `AuditEvents` entry recorded

