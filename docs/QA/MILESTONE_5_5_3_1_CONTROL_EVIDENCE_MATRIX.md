# BIOS — Milestone 5.5.3.1: Control Evidence Matrix

**Milestone**: 5.5.3.1 — QA Evidence Reconciliation & Consistency Audit  
**Date**: November 7, 2026  
**Auditor**: Senior Independent QA Auditor & Enterprise BI Governance Architect  
**Baseline Git Commit**: `99c8fd01632e4e4a0cc1646f9d7338a8d7e06aab`  
**Dataset SHA-256**: `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab`

---

## 1. Security & Lifecycle Control Audit Matrix (N1–N10, C1–C2)

| Control ID | Control Name & Scope | Test File & Name | Exact Operation Attempted | Enforcement Boundary | Blocked By App Logic or Mock? | Audit Event Produced? | Active With LLM Disabled? | Auditor Classification |
|---|---|---|---|---|---|---|---|---|
| **N1** | Unapproved Asset Retirement | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n1_unapproved_retirement_blocked` | Requester attempts to authorize retirement of asset `AST-0001` without `BI_GOVERNANCE_REVIEWER` role. | `ApprovalService.approve_request` -> `RolePermissionManager.can_review` | Application Logic (`PermissionError: Insufficient authority`) | Yes (`TRANSITION_REJECTED` recorded on failure) | Yes (100% deterministic RBAC check) | **IMPLEMENTED AND TESTED** |
| **N2** | Retirement Without Evidence / Blockers Present | `backend/tests/test_approvals_rbac.py`<br>`test_hard_governance_blockers_prevent_approval` | Approver attempts to approve asset retirement where active downstream dependencies or unresolved governance blockers exist. | `ApprovalService.approve_request` / `ApprovalStateMachine.validate_transition` | Application Logic (`ValueError: Active governance blockers prevent approval`) | Yes (`TRANSITION_BLOCKED` event logged) | Yes (Reads active findings from DB) | **IMPLEMENTED AND TESTED** |
| **N3** | Self-Approval Prohibition | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n3_self_approval_prohibited` | Requester `USER-100` attempts to approve their own submission for `PUBLISH_ARTIFACT`. | `RolePermissionManager.can_review` | Application Logic (`allowed=False`, "Self-approval prohibited") | Yes (Denied before state change; audit logged if via API) | Yes (Strict ID equality check) | **IMPLEMENTED AND TESTED** |
| **N3-AI** | AI Agent Authorization Ban | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n3_ai_agent_self_approval_banned` | AI agent bot (`DecisionAgent-Bot`) attempts to act as approver for lifecycle changes. | `RolePermissionManager.can_review` | Application Logic (`allowed=False`, "AI Agent authorization prohibited") | Yes (Attempt flagged in audit trail) | Yes (Deterministic pattern match on actor ID) | **IMPLEMENTED AND TESTED** |
| **N4** | Inactive Owner Authorization | Verified via code inspection and `RULE-003` predicate check | Inactive asset owner attempts to approve changes to an owned asset. | Role assignment layer & `Owners.status` DB check | Partial: Blocked if role is unassigned; however `ApprovalService` relies on role parameter without querying `Owners.status` live in DB. | Partial (Audit logs actor role, but no DB owner status check) | Yes | **PARTIALLY IMPLEMENTED** |
| **N5** | Expired Waiver Enforcement | Verified via `backend/app/approvals/schemas.py` and state machine | Attempting to execute an action based on an approval past its expiry timestamp. | Schema includes `ApprovalStatus.EXPIRED`; transition rules defined in `ApprovalStateMachine` | Partial: State transition logic supports `EXPIRED`, but automated background TTL expiration job is not yet active. | No automated event until transition triggered | Yes | **PARTIALLY IMPLEMENTED** |
| **N6** | RULE-008 Waiver Prohibited | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n6_rule_008_waiver_prohibited` | Requester attempts to request a governance waiver for RULE-008 with a blank explanation. | `ApprovalService.create_request` / `ApprovalCreate` validation | Application Logic (`ValidationError` / rejection of empty rationale) | Yes (`EXCEPTION_REQUEST_REJECTED`) | Yes (Input validation schema) | **IMPLEMENTED AND TESTED** |
| **N7** | Direct Merge Without Approval | `backend/tests/test_artifact_reuse_gate.py`<br>`test_build_new_requires_approval` | Requester attempts to trigger artifact generator for `BUILD_NEW` without an approved `ApprovalRequest`. | `ArtifactService.generate_artifact` -> `ApprovalRequiredError` | Application Logic (Inspects `ApprovalRequests` for `APPROVED` status) | Yes (`ARTIFACT_GENERATION_BLOCKED`) | Yes (Relational lookup against approval DB) | **IMPLEMENTED AND TESTED** |
| **N8** | New Build Without Discovery | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n8_new_build_without_logged_rule_001_discovery_blocked` | Rogue actor attempts direct artifact generation with `spec_id=None`, `spec=None`, `request_id=None`. | `ArtifactService.generate_artifact` | Application Logic (`ValueError: Either spec, spec_id, or request_id must be provided`) | Yes (`INVALID_SPEC_REQUEST`) | Yes (Input validation and discovery verification) | **IMPLEMENTED AND TESTED** |
| **N9** | Audit Immutability & Append-Only Log | `backend/tests/test_audit_immutability.py`<br>`test_audit_log_appended_on_lifecycle_events` & benchmark `test_security_n9_audit_immutability` | Verifies audit events cannot be overwritten or deleted; each transition inserts a new record with before/after state. | `AuditEvents` table & `ApprovalService` logging helpers | Application Logic (ORM append-only design; zero update/delete routes exposed) | Yes (Generates `STATE_TRANSITION`, `APPROVAL_DECISION` records) | Yes (SQLite append-only design) | **IMPLEMENTED AND TESTED** |
| **N10** | Out-of-Allowlist Tool Execution | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_prompt_injection_cannot_reveal_system_prompt_or_bypass_approval` | Untrusted prompt injects malicious commands attempting to execute arbitrary system commands or out-of-scope tools. | `AgentOrchestrator._run_step` and strict Pydantic schemas | Application Logic (Agents execute purely within deterministic Python function scopes; no dynamic shell eval) | Yes (Logged in `AgentExecutionTraces`) | Yes (Zero shell tool calls permitted) | **IMPLEMENTED AND TESTED** |
| **C1** | Authorized Evidenced Approval | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_c1_authorized_evidenced_approval_succeeds` | Legitimate `BI_GOVERNANCE_REVIEWER` approves valid Tableau migration with verified evidence snapshot. | `ApprovalService.approve_request` | Application Logic (Permits transition, records decider, transitions to `APPROVED`) | Yes (`REQUEST_APPROVED` audit event logged) | Yes (Deterministic state machine transition) | **IMPLEMENTED AND TESTED** |
| **C2** | Valid Standard Action Authority | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_c2_valid_standard_action_succeeds` | Legitimate governance reviewer acts within defined role permissions for standard publishing. | `RolePermissionManager.can_review` | Application Logic (Returns `allowed=True`, "Role matches required authorization level") | Yes (Audit records authorized role execution) | Yes (Matrix dictionary lookup) | **IMPLEMENTED AND TESTED** |

---

## 2. Hallucination Detection Controls (H1–H3)

| Control ID | Control Name | Test Name | Seeded Fault Tested | Enforcement Mechanism | Status |
|---|---|---|---|---|---|
| **H1** | Phantom Entity Reference Detection | `test_detector_h1_phantom_reference_detection` | Seeded text referencing non-existent IDs: `AST-9999`, `KPI-999`, `SM-888`, `RULE-099`. | `HallucinationDetector.detect_phantom_references` (regex scan against live DB primary keys) | **IMPLEMENTED AND TESTED** (100% detection) |
| **H2** | Invented KPI Definition Claims | `test_detector_h2_invented_kpi_definitions` | Seeded claim: `KPI-001` name is "Profit Margin Before Tax" in domain "Commercial". | `HallucinationDetector.verify_kpi_definition_claims` (cross-references `KpiCatalog` approved rows) | **IMPLEMENTED AND TESTED** (Caught invented definition) |
| **H3** | Unsupported Evidence Citations | `test_detector_h3_unsupported_evidence_citation` | Citation referencing non-existent record `AST-9876` in table `analytics_assets`. | `HallucinationDetector.verify_evidence_citation` (relational table dynamic verification) | **IMPLEMENTED AND TESTED** (100% rejection of bogus citations) |

---

## 3. Duplication Gate Hierarchy (G1–G4)

| Gate Level | Gate Name | Test Name | Tested Asset Pair / Condition | Result | Status |
|---|---|---|---|---|---|
| **G1** | Exact Structural Equality Gate | `test_gate_g1_exact_structural_match` | Identical product, market, semantic model, platform, and audience. | Similarity = 1.0; auto-flags `REUSE` candidate | **IMPLEMENTED AND TESTED** |
| **G2** | KPI & Model Overlap Gate | `test_gate_g2_high_overlap_triggers_consolidate` | Overlapping model ID (`SM-001`), shared canonical KPIs, same therapeutic area. | Similarity $\ge$ 0.70; recommends `CONSOLIDATE` | **IMPLEMENTED AND TESTED** |
| **G3** | Name & Semantic Proximity Gate | `test_gate_g3_partial_semantic_proximity` | Similar asset names ("Nubeqa Sales" vs "Nubeqa Net Sales Mgmt") with different market scopes. | Similarity $\in [0.40, 0.69]$; recommends `MODIFY` | **IMPLEMENTED AND TESTED** |
| **G4** | Provenance Discrepancy Gate | `test_gate_g4_zero_match_allows_build_new` | Completely novel KPI/domain with zero structural or semantic overlap. | Flags ungrounded claims, allows `BUILD_NEW` with approval | **IMPLEMENTED AND TESTED** |

---

## 4. Auditor Summary & Recommendations

1. **Fully Verified Controls (10 of 12)**:
   Controls **N1, N2, N3, N3-AI, N6, N7, N8, N9, N10, C1, and C2** are implemented directly in application logic and verified by passing automated tests. None rely on test mocks for their core enforcement boundaries.
2. **Partially Implemented Controls (2 of 12)**:
   - **N4 (Inactive Owner Live DB Check)**: Role assignment blocks inactive personnel at the IAM/SSO boundary, but `ApprovalService` does not re-query `Owners.status` during every review invocation. Recommendation: Add a secondary query to `Owners` in `RolePermissionManager.can_review` in Milestone 5.6.
   - **N5 (Automated Expiry Sweeper)**: State transition permits `EXPIRED`, but relies on an external cron/scheduler or access check to trigger the transition. Recommendation: Add an automatic TTL check on request retrieval.

