# BIOS Response Standard

Every assistant response must be understandable to a business user. The answer comes first; governance comes last. The backend produces this structure in `presentation` (`backend/app/agents/answering/presentation.py`); the UI renders it in that order (`frontend/components/assistant/AnswerView.tsx`).

## Common rules

- Lead with the answer in plain language: 2–4 sentences.
- Show units, currency and coverage for every figure.
- No raw JSON, agent logs or chain-of-thought in the main answer. Factual execution steps and evidence sit behind **View AI reasoning and evidence**.
- No uncalibrated confidence percentages. The UI shows what the evidence is ("Computed directly from source records", "Rule-based decision; the score is not a calibrated probability"). The raw internal score stays in the trace.
- Never cite an ID the catalog doesn't contain. An unknown asset ID is described as "the asset ID in the request", not repeated.
- Say when data is missing or unsupported. Fabricated certainty is a failure.

## Analytics asset requests (`ASSET_RECOMMENDATION`)

1. **Recommended action** — REUSE / CONSOLIDATE / MODIFY / MIGRATE / RETIRE / BUILD_NEW / NEEDS_CLARIFICATION, plus the action status (Can proceed / Requires human approval / Blocked by governance / Waiting for your input).
2. **Direct business answer** — what to do and why, in 2–4 sentences.
3. **Why this is the right decision** — matching assets and their trust signals (endorsement, owner, lifecycle, KPI evidence, scope), rejected targets and the reason, gate evidence for consolidation.
4. **Recommended next steps** — concrete actions, including the approval path.
5. **Governance Blockers (N)**
6. **Governance Warnings & Caveats (N)**
7. **Key Governance Directive**

## Business data questions (`DATA_ANSWER`)

1. Direct answer and key figures (figure tiles).
2. Short comparison or trend.
3. Units, currency, aggregation and record coverage, including missing months.
4. Source: `Product_Market_Monthly`, synthetic data, dataset period.
5. Relevant caveats and the canonical KPI directive, at the end.

When the period is outside the dataset: say so, give the available period, and offer the available-period figure only as a clearly labelled reference — never as the answer.

## Governance questions (`GOVERNANCE_ANSWER`)

Answer first ("AST-0268 is blocked: missing accountable owner (RULE-003, critical)."), then the rule's consequence and required action, then the findings list. List answers state the exact total and show up to 25 rows.

## Migration questions (`MIGRATION_RECOMMENDATION`)

Recommendation first (counts per path, direct-migration candidates), then rationale, then governance. Paths are kept separate: direct migration, consolidate before migrating, rebuild on shared model, retire, human review. Each item notes that execution needs an approval request.

## Clarification (`CLARIFICATION`)

Ask only for what is missing, state what is already resolved, and — for asset requests whose scope is resolved — list the existing trusted assets first (reuse before build). Geography clarifications never list assets outside the stated geography.
