# BIOS 1.0 Incident Report: CONSOLIDATE into Unowned AST-0268 (Live LLM Session)

**Date:** 2026-11-07 · **Status:** Root cause found; fixed and verified (rule-based and live Ollama) · Synthetic SinceAI data only.

## 1. The failed request

| Item | Value |
|---|---|
| Request ID | `REQ-20261107181530-C774DB` (the screenshot ID; `…181538…` does not exist in `assistant_requests`) |
| Input | `check nubeqa sales in germany` |
| Created | 2026-11-07 18:15:30 UTC — a **newly executed** request, not a reused stored one |
| Normalized intent | products `[Nubeqa]`, markets `[DE]`, kpis `[sales]` (LLM mapped "sales" → Net Sales; scope unchanged) |
| Agent modes | Intent LLM_ASSISTED (ollama qwen3.5:4b) · Discovery DETERMINISTIC · KPI LLM_ASSISTED · Duplication DETERMINISTIC · Governance DETERMINISTIC · Decision LLM_ASSISTED (narrative only) |
| Discovery | exact matches AST-0157, AST-0240, AST-0268, AST-0270 |
| Governance | 2 RULE-003 blockers on AST-0268 (finding + ownership check) |
| Final decision | `CONSOLIDATE`, target `[AST-0268]`, confidence 0.88 |
| LLM narrative | "We must consolidate requirements into existing asset AST-0268 due to a 96% similarity match… contact the owner of AST-0268…" |

## 2. Where AST-0268 became the target

The deterministic decision matrix of the **pre-fix** `DecisionAgent._decide` (`backend/app/agents/specialists/decision_agent.py`), option B: `if duplication.has_duplicates and duplication.primary_duplicate_asset_id:` → target = the highest composite-similarity candidate, with **no eligibility check**. The LLM did not choose the target; it only wrote the narrative.

## 3. Root cause

1. **Stale backend process.** The API on port 8000 (pid 23524) was started at 19:05:50 local, without `--reload`, before the governance-consistency changes (eligibility, `action_status`, request routing) landed between ~19:30 and 20:05. The stored trace proves it: the DecisionAgent output has no `action_status`, `ineligible_targets` or `validation_notes`, Intent has no `request_types`, Discovery has no `data_answer` — fields every response from the current code carries. With current code this input is a **data question** (answer: €237.10M, Jan–Oct 2026), not an asset decision.
2. **Stale frontend.** Port 3000 serves a `next start` production build started at 19:31:50, before the new answer layout; the screenshot shows the old "Authoritative Decision / Confidence: 88% / Target Enterprise Assets" card.
3. **Real gap that remained in current code:** the LLM narrative guard (`DecisionAgent._narrate`) checked only echoed fields and unknown IDs. A narrative presenting a rejected asset as the target, saying "blocked" when the action wasn't, or directing an action at a non-target asset could pass, and the UI showed the narrative as the main answer. There was also no independent check after the Decision Agent: correctness depended on the agent alone.

Ruled out: LLM overriding the decision (decision fields are computed before the narrative; the guard rejects echo mismatches); reuse of a previous recommendation (new request ID, new traces); provider-specific decision paths (the rule-based and Ollama runs below give identical decisions).

## 4. Fix

- **Mandatory deterministic post-decision validation** — `backend/app/agents/answering/final_validation.py`, `validate_final_decision()`, called by the orchestrator inside the Decision step for every provider, before the result is traced, stored or returned. It re-derives eligibility from the catalog and persisted findings; removes non-existent or ineligible targets (unowned, inactive owner for changes, critical findings, RULE-008 for retirement); sets `BLOCKED` when no eligible target remains or a blocker applies to the target or request; forces approval on consequential/blocked actions (approval never clears a blocker); discards any narrative that cites unknown IDs, presents a rejected asset as usable, directs an action at a non-target asset, omits "blocked" when blocked, or claims "blocked" when not. It never substitutes a target on its own. Outcome recorded in `recommendation.validation_notes`.
- **Narrative guard hardened** (`DecisionAgent._narrate`): the same consistency rules, with `action_status` and `ineligible_target_ids` given to the model.
- **Deterministic text is authoritative in the UI**: the direct answer is `primary_recommendation`; the AI-drafted summary appears only as a labelled, validated supplementary line.
- **RULE-008 retirement protection** moved into the shared eligibility check (`answering/eligibility.py`), so every path enforces it (found by the regression: "Retire AST-0017 now." was REQUIRES_APPROVAL on one path).
- **KPI evidence for direct reuse**: "Can I reuse AST-0157…" becomes MODIFY when Asset_KPI_Map shows the asset lacks the requested KPI.

## 5. Before and after

**Before** (`REQ-20261107181530-C774DB`, stale :8000 backend, Ollama):
```
decision: CONSOLIDATE   target_asset_ids: ["AST-0268"]   action_status: (absent)
blockers: 2 × RULE-003 on AST-0268   narrative: "We must consolidate requirements into existing asset AST-0268 …"
```

**After** (current code, live Ollama qwen3.5:4b, through the real frontend; full JSON in `docs/QA/live_llm_nubeqa/`):

| ID | Prompt | Request | Decision | Status | Target |
|---|---|---|---|---|---|
| N1 `REQ-20261107183437-A3DB0D` | check nubeqa sales in germany | DATA_QUESTION | INFORMATIONAL — €237.10M, Jan–Oct 2026, 10 records | No action proposed | — |
| N2 `REQ-20261107183444-1701A9` | I need a scoreboard for Nubeqa sales in Germany. | ASSET_REQUEST | MODIFY | Requires approval | AST-0240 (AST-0268 rejected) |
| N3 `REQ-20261107183451-9750A2` | Consolidate the Nubeqa Germany dashboards into AST-0268. | ASSET_REQUEST | CONSOLIDATE | **Blocked** | none |
| N4 `REQ-20261107183455-F17AC9` | Can I reuse AST-0157 for Nubeqa sales in Germany? | ASSET_REQUEST | MODIFY (not reusable as-is) | Requires approval | AST-0157 |

All four: LLM_ASSISTED steps ran; UI action, status and answer match the API; no unowned target.

## 6. Source evidence for the Nubeqa Germany targets (workbook)

| Asset | Lifecycle / endorsement | Owner | KPIs (Asset_KPI_Map) | Verdict |
|---|---|---|---|---|
| AST-0268 | legacy / none | **none** | KPI-001 Net Sales (approved), KPI-034, KPI-003, KPI-032, KPI-048 | Only DE asset with Net Sales, but never actionable (RULE-003) |
| AST-0240 | active / none | OWN-046, active | KPI-004 Net Sales Growth (approved), KPI-045, KPI-049, KPI-055 | Best eligible: active, owned, same KPI family → extend, not reuse |
| AST-0157 | **legacy** / promoted | OWN-051, active | only draft KPIs (KPI-015, KPI-032, KPI-052) | No sales KPI → not reusable as-is |
| AST-0270 | active / none | OWN-056, active | KPI-049, KPI-048 | No sales KPI |

## 7. Regression results (both providers)

`backend/scripts/run_provider_regression.py` → `docs/QA/BIOS_PROVIDER_REGRESSION_RESULTS.json`. Rule-based backend `BIOS_LLM_PROVIDER=deterministic`; LLM backend `BIOS_LLM_PROVIDER=ollama`, model qwen3.5:4b (local), 1–3 live LLM steps per request recorded in trace metadata.

| Scenario | Rule-based | LLM-assisted |
|---|---|---|
| Exact failed request | INFORMATIONAL ✔ | INFORMATIONAL ✔ |
| Nubeqa Germany scoreboard | MODIFY AST-0240 ✔ | MODIFY AST-0240 ✔ |
| Unowned AST-0268 consolidation | CONSOLIDATE, BLOCKED ✔ | CONSOLIDATE, BLOCKED ✔ |
| AST-0157 reuse | MODIFY (KPI gap) ✔ | MODIFY (KPI gap) ✔ |
| Eligible consolidation (Hyrnuo US) | CONSOLIDATE → AST-0147 ✔ | same ✔ |
| No eligible target (AST-0026) | MODIFY, BLOCKED ✔ | same ✔ |
| RULE-008 protected retirement (AST-0017) | RETIRE, BLOCKED ✔ | same ✔ |
| Unsupported asset ID (phantom AST-9999) | NEEDS_CLARIFICATION, ID not echoed ✔ | same ✔ |
| Policy: build on unowned asset | BLOCKED ✔ | same ✔ |
| Prompt injection | not BUILD_NEW ✔ | same ✔ |
| **Total** | **10/10** | **10/10** (run twice) |

Live-LLM guardrail activity observed: one narrative rejected for citing a malformed ID ("RULE-08"); one narrative ("the action is blocked…" for a permitted MODIFY) led to the reverse-claim check now in place.

**Expired waiver (N5):** waiver expiry is enforced synchronously in the approvals service and is provider-independent; covered by the existing `backend/tests/test_reliability_n4_n5.py` (passing). It was not run through the LLM backend because no assistant step reads waivers.

Automated tests: `backend/tests/test_llm_governance_override.py` (17 tests) uses a hostile live adapter that proposes extra scope, consolidation into AST-0268, phantom IDs, wrong decision echoes, provider timeouts and false "blocked"/"go ahead" narratives, and calls the validator directly with the exact pre-fix decision. All pass.

## 8. Verification summary

- Backend: **479 passed, 14 skipped**.
- Frontend: 8/8 node tests; `tsc --noEmit` clean; production build succeeded.
- 1,000-question benchmark (rule-based): 999/1000, unchanged.
- `/arduino` 404; RULE-005 500/250, N4, N5, N6 and all eight rules unchanged.

## 9. Action required and limitations

- **Restart the servers on ports 8000 and 3000.** They are still running pre-fix code (I was not permitted to stop them). Backend: stop it and rerun `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend` (add `--reload` during development). Frontend: stop `next start`, run `npm run build`, then `npm run start` (or use `npm run dev`). The post-fix verification above used the same code on ports 8001/8002/3002.
- Live-LLM verification covers qwen3.5:4b on this machine only; other models may write different narratives, which the guard and validator will discard when inconsistent (the decision is unaffected).
- The header label "Backend Operational (Port 8000)" is static text and doesn't reflect the actual proxy target.
- The validator blocks rather than choosing a substitute target; alternatives are evaluated by the Decision Agent before validation.
