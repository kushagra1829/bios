# BIOS AI Intelligence Architecture

**Principle:** build less, build better, govern intelligently. BIOS answers the question the user actually asked, discovers existing trusted analytics before proposing anything new, and never lets an AI proposal override a deterministic governance decision.

All data is the synthetic SinceAI 2026 Builder Data Pack. Nothing here represents Bayer business performance or a Bayer deployment.

## 1. Request types

Every request is classified by a deterministic router (`backend/app/agents/request_router.py`) before any agent acts. A request can carry several types; the first is primary.

| Type | Example | Workflow | Decision returned |
|---|---|---|---|
| `DATA_QUESTION` | "What were Nubeqa sales in Germany in Q1 2026?" | Query `Product_Market_Monthly`, deterministic aggregation | `INFORMATIONAL` (or `NEEDS_CLARIFICATION`) |
| `ASSET_REQUEST` | "I need a Nubeqa sales scoreboard for Germany." | Discover → KPI check → G1–G4 → governance → decide | `REUSE` / `CONSOLIDATE` / `MODIFY` / `MIGRATE` / `RETIRE` / `BUILD_NEW` / `NEEDS_CLARIFICATION` |
| `GOVERNANCE_QUESTION` | "Why is AST-0268 blocked?" | Read persisted governance findings and catalog | `INFORMATIONAL` |
| `MIGRATION_QUESTION` | "Which Nubeqa dashboards should be migrated?" | Read `Migration_Backlog` + findings | `INFORMATIONAL` (list), or a per-asset path decision |

Combined requests ("Check Nubeqa sales and tell me whether we need a new dashboard") return a data answer **and** a separate asset recommendation.

Routing rules worth knowing:
- A measure becomes a data question only with a question or command form ("What were…", "Show…", "Compare…", "Which product had…"). Terse intake phrasing such as "Sales in Finland" keeps the earlier asset-request contract.
- Imperative build or change requests ("Build…", "Promote AST-0088…") are asset requests whatever nouns follow.
- Routing never consults an LLM, so it is identical across providers.

## 2. Six-agent orchestration (preserved)

The orchestrator still runs exactly six agents, one at a time, with a persisted trace per step.

| Agent | Responsibility added in this release |
|---|---|
| 1 Intent | Adds `request_types`, router evidence, mentioned asset IDs, duplication-question flag and asset-title topics (e.g. "Budget Management" → `budget mgmt`). Products and markets remain parser-decided; Europe is never converted to EMEA. |
| 2 Discovery | Searches the catalog as before; also treats named asset IDs as the request's subject and retrieves the evidence for question types: the **data answer** (`backend/app/analytics/data_query.py`), **governance answer** (`answering/governance_answers.py`) and **migration answer** (`answering/migration_answers.py`). |
| 3 KPI Intelligence | Unchanged: canonical vs local KPIs, approval status, conflicts. |
| 4 Duplication | Composite similarity as before, plus staged **G1–G4 gate evaluation** of real in-scope asset pairs and same-title groups, so title similarity alone can never justify consolidation. |
| 5 Governance | Unchanged deterministic engine and all eight rules; the RULE-001 directive now names the asset's actual endorsement level. |
| 6 Decision | Answers questions without inventing actions; applies **target eligibility** before every asset action; sets `action_status`. |

**Mandatory post-decision validation** (`answering/final_validation.py`, `validate_final_decision`) runs inside the Decision step for every provider, after any LLM narrative and before the result is traced, stored or returned:

```
request → intent → discovery → KPI → duplication → deterministic governance
        → decision (+ optional LLM narrative) → deterministic final validation → API → presentation
```

It removes non-existent or ineligible targets, blocks the action when no eligible target remains or a blocker applies, forces approval on consequential or blocked actions (approval never clears a blocker), and discards any narrative that contradicts the validated decision. It never substitutes a target itself. Its outcome is in `recommendation.validation_notes`. The UI's direct answer is always the deterministic `primary_recommendation`; the AI narrative is a labelled supplementary line. See `docs/QA/BIOS_LIVE_LLM_DECISION_INCIDENT_REPORT.md`.

A deterministic **presentation layer** (`answering/presentation.py`, not an agent) turns the agents' output into the business response standard and deduplicates findings.

## 3. Governance consistency

`answering/eligibility.py` decides whether an asset may be the target of an action:

| Condition | Effect |
|---|---|
| No accountable owner (RULE-003 critical) | Never a target for reuse, modification, consolidation, migration or retirement. |
| Inactive owner (RULE-003 high) | Blocks change actions (no owner authority, N4); reuse allowed with a warning. |
| Any other critical persisting finding | Blocks the action on that asset. |
| Lifecycle `legacy` / `candidate_retire` | Reuse allowed with an owner-confirmation step and warning. |

If the best-scoring candidate is ineligible (e.g. AST-0268), the Decision Agent moves to the next eligible candidate and reports the rejected one in `ineligible_targets`. If none is eligible the decision is returned with `action_status = BLOCKED` and no target. Blockers on non-target assets no longer suppress reuse of a different, eligible asset; request-level blockers (unapproved high-criticality KPI, security override) still block.

`action_status`: `ACTIONABLE`, `REQUIRES_APPROVAL`, `BLOCKED`, `NEEDS_INPUT`, `NOT_APPLICABLE`.

Unchanged and verified by the existing suite: all eight governance rules, RULE-005 thresholds (500 / 250), N4 owner authority, N5 synchronous waiver expiry, N6 RULE-008 protection, backend RBAC, the provider-independent adapter, and `/arduino` → 404.

## 4. Data answers

`DataQueryEngine` reads `product_market_monthly` (one record per product × market × month, Jan–Oct 2026).

- Measures: net sales and forecast (M EUR, summed), units shipped (summed), market access coverage / OTIF (%), inventory coverage (weeks) — percentage-type measures are reported as the unweighted mean, and the answer says so.
- Operations: total, average, trend, compare (products, markets or periods), rank, forecast vs actual, change.
- Periods: years, quarters, halves, months, ranges, YTD, last N months, last quarter. Requested months outside the dataset are reported as missing (`PARTIAL` / `NO_DATA`), never extrapolated.
- Unsupported metrics (market share, profit, prescriptions, gross-to-net, budget…) and unknown products/markets return `UNSUPPORTED` with no figures.
- Every answer carries coverage (records used vs expected, missing months, `value_type` label counts), unit, aggregation and source.

Verified field fact: `forecast_variance_pct = (net − forecast) / forecast × 100` on all 870 non-null records; 110 are null and are never imputed.

## 5. API contract changes (additive)

`POST /api/v1/assistant/requests` keeps every existing field. Added:

- `request_types`, `data_answer`, `governance_answer`, `migration_answer`, `presentation`
- `recommendation.action_status`, `recommendation.ineligible_targets`
- `DecisionType` gains `RETIRE` and `INFORMATIONAL`
- `discovery.data_answer|governance_answer|migration_answer|title_topic_matches`, `duplication.gate_evaluations|consolidation_eligible_pairs|title_alike_groups`

No database model or design token changed.

## 6. Files

| Area | Files |
|---|---|
| Routing | `backend/app/agents/request_router.py` |
| Data answers | `backend/app/analytics/data_query.py` |
| Governance / migration answers | `backend/app/agents/answering/governance_answers.py`, `migration_answers.py` |
| Target eligibility | `backend/app/agents/answering/eligibility.py` |
| Presentation | `backend/app/agents/answering/presentation.py` |
| Agents | `intent_agent.py`, `discovery_agent.py`, `duplication_agent.py`, `governance_agent.py`, `decision_agent.py`, `orchestrator.py`, `schemas.py` |
| UI | `frontend/components/assistant/AnswerView.tsx`, `frontend/app/assistant/page.tsx`, `frontend/lib/types.ts` |
| Benchmark | `backend/scripts/generate_ai_benchmark.py`, `run_ai_benchmark.py`, `run_ui_journeys.py` |
