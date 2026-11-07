# BIOS — Milestone 3: Analytics Lifecycle & Migration Intelligence Engine

## 1. Overview & Objectives

Milestone 3 implements the explainable lifecycle optimization and Tableau-to-Power BI migration intelligence engine for BIOS.
The engine:
- Evaluates all **360 analytics assets** in the estate across multi-dimensional usage, reach, governance, lineage, KPI quality, and semantic health criteria.
- Applies **non-negotiable hard governance safeguards** to prevent accidental or premature retirement of critical reports.
- Classifies the **94 legacy Tableau assets** into actionable modernization paths (`MIGRATE`, `CONSOLIDATE_BEFORE_MIGRATION`, `RETIRE_INSTEAD_OF_MIGRATE`, `FIX_BEFORE_MIGRATION`, `HOLD_FOR_REVIEW`).
- Enables Bayer to achieve an estimated **48.9% migration effort reduction** by eliminating redundant reports and retiring dead content prior to rebuilding in Power BI / Fabric.
- Connects directly into the Milestone 2 multi-agent Decision Agent to provide evidence-backed recommendations for incoming business requests.

---

## 2. Published Scoring Formula & Weights

The lifecycle health score is a normalized 0.0 to 100.0 composite index:

$$S_{\text{composite}} = 0.25 S_{\text{usage}} + 0.20 S_{\text{reach}} + 0.20 S_{\text{gov}} + 0.15 S_{\text{lineage}} + 0.10 S_{\text{kpi}} + 0.10 S_{\text{semantic}}$$

### Component Sub-Scores:
1. **Usage Recency & Reliability ($S_{\text{usage}}$, 25% weight)**:
   - Views Volume: $\min(100.0, \frac{\text{avg\_views}}{250.0} \times 100.0)$
   - Active Users: $\min(100.0, \frac{\text{avg\_users}}{50.0} \times 100.0)$
   - Query Errors Penalty: Subtracts up to 20 points for high error counts.
   - Formula: $0.6 \times \text{views\_score} + 0.4 \times \text{users\_score} - \text{penalty}$.
2. **Audience Reach & Criticality ($S_{\text{reach}}$, 20% weight)**:
   - Audience Reach: $\min(80.0, \frac{\text{estimated\_audience}}{1500.0} \times 80.0)$
   - Criticality Boost: $+20.0$ points if classification is `confidential` or any mapped KPI has `business_criticality == 'critical'`.
3. **Governance Trust ($S_{\text{gov}}$, 20% weight)**:
   - Endorsement: Certified = 100.0, Promoted = 75.0, None = 25.0.
   - Ownership: Active Owner = 100.0, Inactive Owner = 30.0, Unowned (`NULL`) = 0.0.
   - Formula: $0.5 \times \text{endorsement\_score} + 0.5 \times \text{owner\_score}$.
4. **Lineage & Dependency ($S_{\text{lineage}}$, 15% weight)**:
   - Downstream Consumers: $50.0 + \min(50.0, \text{downstream\_dependents} \times 25.0)$ for assets with downstream reports.
   - Upstream Traceability: 50.0 if registered in lineage; 20.0 if disconnected orphan.
5. **KPI Quality ($S_{\text{kpi}}$, 10% weight)**:
   - Ratio of mapped KPIs that are canonical and approved: $\frac{\text{canonical\_approved}}{\text{total\_mapped}} \times 100.0$.
6. **Semantic Model Health ($S_{\text{semantic}}$, 10% weight)**:
   - Model AI Readiness: Good = 100.0, Partial = 60.0, Poor = 20.0.
   - Model Refresh Health: Healthy = 100.0, Warning = 50.0, Failed = 0.0.

---

## 3. Non-Negotiable Hard Governance Safeguards (Veto Rules)

The engine enforces strict vetoes before any retirement action can be recommended:

1. **Downstream Dependency Veto**:
   - If an asset has $\ge 1$ downstream dependent reports in `LineageEdges` (`edge_type == 'ASSET_TO_ASSET'`), **retirement is strictly vetoed**.
   - The recommendation is forced to `HOLD_FOR_REVIEW` or `CONSOLIDATE`, with risks explicitly warning: *"Lineage Dependency Anchor: X downstream reports depend on this asset."*
2. **Certified Endorsement Veto**:
   - Endorsed assets (`certified` or `promoted`) cannot be casually retired, even if usage has tapered. They are routed to `REVIEW` with BI leadership sign-off required.
3. **Active Usage Safeguard**:
   - Assets marked as `candidate_retire` in source metadata that maintain active usage ($\text{avg\_views} \ge 50.0$) cannot be retired immediately; they are routed to `CONSOLIDATE`.
4. **Insufficient Evidence Safeguard**:
   - Assets with missing usage telemetry are never assigned automated decommission decisions; they are forced to `REVIEW` with confidence $\le 0.50$.
5. **Tableau Platform Routing**:
   - All 94 Tableau assets are routed to `MIGRATE` in estate lifecycle view and evaluated by the dedicated migration intelligence engine.

---

## 4. Real Dataset Portfolio Results

Evaluated across the entire synthetic challenge data pack:

### A. Estate Lifecycle Overview (360 Assets)
- **Average Composite Score**: **58.5 / 100.0**
- **Action Breakdown**:
  - `MIGRATE`: **94** (Tableau legacy platform assets)
  - `CONSOLIDATE`: **102** (Redundant variants / legacy assets with active business usage)
  - `REVIEW`: **105** (Vetoed retirements with downstream consumers, unowned assets, or governance reviews)
  - `IMPROVE`: **55** (High-value assets needing owner reassignment, ETL refresh repair, or KPI canonicalization)
  - `KEEP`: **3** (High-health certified production assets)
  - `RETIRE_CANDIDATE`: **1** (Zero downstream dependents, low usage, unendorsed, safe for decommissioning)
- **Key Portfolio Metrics**:
  - Assets blocked from retirement by downstream dependencies: **35**
  - Unowned assets flagged for remediation: **14**
  - High-value assets with active governance risks: **24**
  - Total rationalization opportunities: **103**

### B. Tableau Migration Rationalisation (94 Assets)
- **Direct Migrate (`MIGRATE`)**: **13** (Clean candidates ready for rebuild on target model)
- **Consolidate Before Migration (`CONSOLIDATE_BEFORE_MIGRATION`)**: **30** (Redundant logic consolidated into shared model)
- **Fix Before Migration (`FIX_BEFORE_MIGRATION`)**: **20** (Target semantic models require refresh or naming repair)
- **Retire Instead of Migrate (`RETIRE_INSTEAD_OF_MIGRATE`)**: **16** (Obsolete low-use reports with 0 dependents)
- **Hold for Review (`HOLD_FOR_REVIEW`)**: **15** (High-impact reports with active downstream consumers)
- **Estimated Migration Effort Reduction**: **48.9%** (46 of 94 reports avoided from 1:1 rebuild).

---

## 5. API Endpoints

Mounted under `/api/v1/lifecycle` and `/api/v1/migration`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/lifecycle/evaluate` | Triggers estate-wide evaluation and persists runs. |
| `GET` | `/api/v1/lifecycle/summary` | Estate-level summary, average scores, dependency blocks, rationalization counts. |
| `GET` | `/api/v1/lifecycle/recommendations` | Paginated asset recommendations with score breakdowns and risk flags. |
| `GET` | `/api/v1/lifecycle/recommendations/{id}` | Detailed assessment for a specific asset. |
| `GET` | `/api/v1/migration/summary` | Tableau migration portfolio summary and effort reduction %. |
| `GET` | `/api/v1/migration/recommendations` | Individual Tableau migration assessments with target models and complexity. |

---

## 6. Test Suite & Verification

The test suite contains **75 automated tests** running in **< 9 seconds**:
- `test_lifecycle_scoring.py` (3 tests): Formula weights integrity, endorsement/ownership impact, downstream dependency scoring.
- `test_lifecycle_rules.py` (5 tests): Downstream dependency vetoes, certified endorsement protection, active usage safeguards, insufficient evidence handling, Tableau routing.
- `test_migration_intelligence.py` (3 tests): Tableau evaluation across 94 assets, dependency vetoes on retirement, 48.9% effort reduction calculation.
- `test_lifecycle_api.py` (6 tests): Endpoints, parameter filtering, pagination, and 404 handlers.
- Backward compatibility: All 24 Milestone 0, 20 Milestone 1, and 14 Milestone 2 tests pass 100%.

