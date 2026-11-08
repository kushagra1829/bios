# BIOS Intent Routing Tests

Routing is deterministic (`backend/app/agents/request_router.py`) and tested in `backend/tests/test_ai_intelligence_transformation.py`.

## Routing table (asserted in tests)

| Prompt | Request types |
|---|---|
| What were Nubeqa sales in Germany in Q1 2026? | DATA_QUESTION |
| Show monthly sales trends for Nubeqa. | DATA_QUESTION |
| Compare Nubeqa and other products in Germany. | DATA_QUESTION |
| I need a Nubeqa sales dashboard for Germany. | ASSET_REQUEST |
| Build a scoreboard for European sales. | ASSET_REQUEST |
| Why is AST-0268 blocked? | GOVERNANCE_QUESTION |
| Which reports use non-canonical KPIs? | GOVERNANCE_QUESTION |
| Which Tableau dashboards should be migrated? | MIGRATION_QUESTION |
| Which reports can be retired? | MIGRATION_QUESTION |
| Check Nubeqa sales and tell me whether we need a new dashboard. | DATA_QUESTION, ASSET_REQUEST |
| Sales in Finland | ASSET_REQUEST (terse intake phrasing; earlier contract kept) |

## The 10 regression cases

All pass through the live API (benchmark run) and the test suite.

| # | Prompt | Required behaviour | Result |
|---|---|---|---|
| 1 | Check Nubeqa sales in Germany for 2024–2025. | Data analysis, not CONSOLIDATE | `INFORMATIONAL`, `NO_DATA`: dataset covers Jan–Oct 2026 only; no figures invented |
| 2 | I need a scoreboard for Nubeqa sales in Germany. | Discover before BUILD_NEW | `MODIFY` AST-0240 (owned, active, maps Net Sales Growth); AST-0268 rejected as target (no owner) |
| 3 | We already have three similar Nubeqa dashboards. What should we do? | Evidence-based duplication assessment | `NEEDS_CLARIFICATION`: G1–G4 ran; no Nubeqa pair passes; same-title groups are in different markets; asks which assets |
| 4 | Why is AST-0268 blocked? | Explain missing owner, RULE-003 | Governance answer citing RULE-003 critical and the required action |
| 5 | Find the certified dashboard for Nubeqa Budget Management. | Verified catalog match | `REUSE` AST-0073 — the only certified "Nubeqa Budget Mgmt"; lifecycle `candidate_retire` flagged with an owner-confirmation step |
| 6 | Create another dashboard for the same Nubeqa KPIs. | Reuse-first | `NEEDS_CLARIFICATION` listing existing endorsed, active Nubeqa assets; no BUILD_NEW |
| 7 | Which Nubeqa dashboards should be migrated to Power BI? | Actual migration records | 8 backlog records: 3 direct migration (AST-0065, AST-0126, AST-0207), 5 consolidate before migrating |
| 8 | Compare Nubeqa and other products in Germany. | Only supported products/measures | Net sales for all 7 products in DE (Nubeqa €237.10M first); states net sales was assumed because no measure was named |
| 9 | Show Nubeqa sales in Europe. | Europe ≠ EMEA | `NEEDS_CLARIFICATION`; EMEA markets offered as suggestions only, no figures |
| 10 | Build a dashboard using an asset with no accountable owner. | Blocker and safe alternative | `MODIFY`, `BLOCKED`, RULE-003; two safe alternatives offered |

## Changes to earlier test expectations

Routing changed the decision for some requests that earlier milestones treated as asset requests. Only one earlier expectation was edited:

- `backend/tests/benchmarks/test_milestone_5_9_intelligence_benchmark.py`, REQ-BM-030 ("Perform estate rationalization and modernization evaluation for AST-0065…"): `MIGRATE` added to the acceptable decisions, because the answer now comes from AST-0065's actual Migration_Backlog record (path MIGRATE, in progress, target SM-067). The line carries a comment explaining this.

All other earlier tests pass unchanged (462 passed, 14 skipped).

## Known routing ambiguity

"Retire the abandoned legacy Tableau report." — the benchmark label is MIGRATION_QUESTION. The current router returns ASSET_REQUEST first, then MIGRATION_QUESTION, because of a rule (lines ~179–180 of `request_router.py`) that was added to the working tree outside this workstream. The decision is correct either way (`NEEDS_CLARIFICATION`: BIOS won't pick an unnamed asset to retire). The rule was left in place; it is the only benchmark failure.
