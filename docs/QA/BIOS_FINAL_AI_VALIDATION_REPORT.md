# BIOS Final AI Validation Report

**Date:** 2026-11-07 · **Scope:** Final AI Intelligence Transformation (request routing, data answers, reuse-first decisions, governance consistency, response standard, 1,000-question benchmark, UI acceptance journeys).
All data is the synthetic SinceAI 2026 Builder Data Pack. BIOS is not deployed at Bayer, and no Bayer production data was used.

## 1. Result summary

| Gate | Result | Evidence |
|---|---|---|
| Four request types route correctly | Pass | Routing tests; benchmark intent 999/1000 |
| Data questions return data-backed calculations | Pass | 364/364 numeric checks vs independent workbook sums |
| Asset requests discover before recommending | Pass | Reuse decisions 120/120; BUILD_NEW only with zero candidates (J6) |
| Governance blockers prevent prohibited actions | Pass | 185/185 decisions with no unowned/forbidden target; 9/9 blocked where required |
| Findings simplified, deduplicated, shown last | Pass | Presentation tests; J4/J5 screenshots |
| Exactly 1,000 distinct questions with honest labels | Pass | 750 deterministic, 216 dataset-signal, 14 adjudication, 20 insufficient-data |
| 10 regression cases | Pass | 10/10 |
| Security invariants and thresholds unchanged | Pass | Existing suite (RULE-005 500/250, N4, N5, N6, RBAC) passes; `/arduino` → 404 on frontend and backend |
| Existing backend and frontend tests | Pass | 462 passed, 14 skipped (backend); 8/8 (frontend) |
| Next.js production build | Pass | `npm run build` succeeded |
| Six UI journeys | Pass | 6/6, see §3 |

## 2. Test results

- `backend\.venv\Scripts\python.exe -m pytest backend/tests` → **462 passed, 14 skipped** (422 pre-existing + 40 new in `backend/tests/test_ai_intelligence_transformation.py`). The 14 skips are the opt-in live-Ollama and similar tests, unchanged.
- `node --test frontend/tests/assistant_regression.test.mjs` → **8 passed**.
- `npm run build` (frontend) → success; TypeScript `tsc --noEmit` clean.

New tests cover: intent routing, data-vs-asset separation, independent numerical checks (totals, forecast vs actual), partial periods, combined requests, geography (Europe ≠ EMEA, region expansion), measure/KPI resolution, unowned-target exclusion, blocked modification, policy block, title-similarity non-consolidation, gate-backed consolidation, phantom asset handling, finding deduplication with backend counts, approval on consequential actions, unsupported metrics, year-over-year without a prior year, governance and migration answers, and API response structure.

## 3. Product acceptance journeys (real UI + real backend)

Run by `backend/scripts/run_ui_journeys.py`: Playwright drives the installed Chrome against the production build of the Next.js app (port 3001), which proxies to the FastAPI backend (port 8001, deterministic provider). For each journey the script types the prompt, clicks **Analyze Intent**, captures the actual `POST /api/v1/assistant/requests` response, checks that the UI shows the backend's answer, takes screenshots, and verifies evidence against the workbook independently. Artifacts: `docs/QA/journeys/` (`J*_answer.png`, `J*_reasoning.png`, `J*_api_response.json`, `JOURNEY_RESULTS.json`).

| # | Prompt | Outcome | Independent verification |
|---|---|---|---|
| J1 | What were Nubeqa sales in Germany in Q1 2026? | Answer: €59.52M (Jan–Mar 2026), 3 of 3 records, M EUR | Workbook sum of `net_sales_m_eur_syn` for P-NUB/DE Jan–Mar = 59.52 |
| J2 | Build a Kerendia sales scorecard for Finland. | REUSE AST-0292, can proceed | AST-0292 is Kerendia/FI, endorsed, active owner, maps KPI-001 |
| J3 | I need a Hyrnuo net sales dashboard for the US, but we already have overlapping reports there. | CONSOLIDATE AST-0056 into AST-0147, requires approval | Same product/market in workbook, shared KPIs, target owned |
| J4 | Add forecast variance to AST-0268. | MODIFY, blocked by governance, no target | AST-0268 `owner_id` is empty in the workbook; RULE-003 blocker shown |
| J5 | Why is AST-0268 blocked? | Governance answer citing RULE-003 critical; findings last, deduplicated | Owner empty in workbook |
| J6 | New monthly Certified Asset Share dashboard for Japan | BUILD_NEW, requires approval | Discovery searched all 360 assets, 0 candidates; Governance Agent ran |

No journey failed, so none needed a fix-and-retest cycle in the final run. (During development, J-equivalents surfaced the duplicated "why" sentence in J4, which was fixed before the final run.)

## 4. Benchmark

Full results: `docs/AI/BIOS_1000_QUESTION_BENCHMARK_REPORT.md`, raw `docs/AI/BIOS_1000_QUESTION_BENCHMARK_RESULTS.json`.

- **999/1000** questions passed every check; per-category 100% except K (29/30).
- Numerical accuracy 364/364; record coverage 318/318; date filters 318/318; geography 342/342.
- Hallucinated IDs: 0. Unsupported claims: 0 of 49 no-data/unsupported questions.
- Governance consistency: 185/185 asset decisions with no unowned or forbidden actionable target; human approval on 169/169 consequential decisions.
- The only failure: "Retire the abandoned legacy Tableau report." routes ASSET_REQUEST + MIGRATION_QUESTION instead of MIGRATION_QUESTION, due to a router rule added to the working tree outside this workstream (left in place). The decision is still the correct NEEDS_CLARIFICATION.

**Caveat on the score:** the benchmark and the fixes came from the same workstream; the first full run scored 969/1000, and the generic routing gaps it exposed were then fixed. No answers are hard-coded, but question templates share phrasing, so treat 99.9% as a regression-suite result rather than general accuracy on unseen phrasing.

## 5. Behaviour changes worth knowing

- Data questions now return `INFORMATIONAL` with a `data_answer` instead of an asset decision.
- Consolidation, modification and reuse never target an unowned or critically-blocked asset; such assets appear in `ineligible_targets`.
- Blockers on non-target assets no longer suppress reuse of a different eligible asset.
- Reuse targets need KPI evidence when KPIs are requested.
- Phantom asset IDs produce a clarification and are never echoed.
- One earlier test expectation changed (REQ-BM-030 accepts MIGRATE, matching the asset's Migration_Backlog record), documented in `docs/AI/BIOS_INTENT_ROUTING_TESTS.md`.

## 6. Known limitations

- Terse phrases without a question word ("Nubeqa net sales Germany March 2026") are treated as asset requests, preserving the earlier intake contract; users must ask "What were…" or "Show…" to get figures.
- For a product/market with no asset (e.g. Lynkuet/Brazil) BIOS proposes extending a same-product asset from another market, and says so; BUILD_NEW is offered as the alternative. Whether that is preferable is a business judgement.
- Percentage measures are aggregated as unweighted means; the KPI catalog defines no cross-market weighting.
- KPI catalog descriptions contain no formulas, so BIOS reports catalog status but cannot state calculation definitions.
- `docs/DATA_DICTIONARY.md` lists `value_type` as a single value `synthetic_commercial_measure`; the workbook actually contains `actual_like_synthetic` (491) and `forecast_like_synthetic` (489). BIOS reports these labels in coverage. The data dictionary was not edited.
- Benchmark and journeys ran with the deterministic provider. LLM-assisted runs (Ollama) affect only advisory narrative and KPI review text; this was not re-measured here.
- Building the frontend (`npm run build`) writes `.next`, which a running `next dev` also uses; if the dev server on :3000 misbehaves, restart it.

## 7. Unverified integrations

- Power BI publication: not attempted; not claimed (G4 Desktop rendering still pending, as before).
- Gemini and Claude adapters: not implemented (unchanged).
- n8n: optional, not exercised.
- Live Ollama inference: not part of this validation run.
