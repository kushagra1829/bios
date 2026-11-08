# BIOS Governance Presentation Standard

Governance information is always shown **after** the answer, under three headings:

- **Governance Blockers (N)** — findings that prevent the recommended action, or prevent using a specific asset as a target.
- **Governance Warnings & Caveats (N)** — findings that require review, and data caveats.
- **Key Governance Directive** — reuse and policy directives (e.g. RULE-001 reuse before build, RULE-002 use the canonical KPI).

## Each finding shows

`RULE-ID SEVERITY · ASSET-ID: short explanation (effect)` and, expanded on click, the required action, the backend finding IDs and how many backend entries were merged.

Effect labels: **Prevents the action**, **Requires review**, **Informational**.

Example (from "I need a scoreboard for Nubeqa sales in Germany."):

```
Governance Blockers (2)
- RULE-003 CRITICAL · AST-0268: Using this asset as the target is blocked pending owner assignment. (Prevents the action)
- RULE-003 CRITICAL · AST-0268: No accountable owner is assigned. The asset cannot be safely extended until
  ownership is established. AST-0268 is therefore not used as a target for this request. (Prevents the action)
Governance Warnings & Caveats (3)
- RULE-005 HIGH · AST-0268: Unendorsed high-reach asset AST-0268 (audience: 1199). (Requires review)
Key Governance Directive (1)
- RULE-001: Promoted asset AST-0157 ('Nubeqa Budget Mgmt') already serves this exact scope. Reuse must be prioritized...
```

The two RULE-003 blockers are genuinely different controls (missing owner; target eligibility), so both are shown.

## Deduplication

Key: `(kind, rule ID, entity ID, control)`. Control is derived per rule (RULE-003: owner missing / owner inactive / target blocked; RULE-002: the KPI ID; RULE-001: reuse directive vs duplicate title). The Governance Agent's finding-based blocker and its ownership check for the same asset collapse into one entry; the merged backend strings are kept in `sources`.

The backend counts are preserved separately: `backend_blocker_count`, `backend_warning_count` versus `displayed_*_count`, and the UI states both. Nothing is hidden to look cleaner.

## Ordering and scope

1. Findings that affect the recommended target or the whole request first, then others.
2. Within that, by severity (critical, high, medium, low).
3. Findings on assets outside the requested scope are never shown as blockers; only their count is shown, with details in the reasoning panel.

## Effect on actions

Presentation never changes a decision. The Decision Agent has already applied target eligibility: a blocker on the target sets `action_status = BLOCKED` and removes the target; the UI then shows "Blocked: approval can't be requested until the governance blockers are resolved."
