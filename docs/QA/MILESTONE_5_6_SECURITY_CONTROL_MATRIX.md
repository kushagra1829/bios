# BIOS — Milestone 5.6: Reconciled Security Control Evidence Matrix

**Document Version**: 2.0.0 (Milestone 5.6 Reconciled Baseline)  
**Date of Audit**: November 7, 2026  
**Auditor**: Senior Independent QA Auditor & Application Security Engineer  
**Baseline Git Commit**: `99c8fd01632e4e4a0cc1646f9d7338a8d7e06aab`  
**Dataset SHA-256**: `7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab`  
**Test Suite Results**: 410 collected; 396 passed, 14 skipped, 0 failed  

---

## 1. Executive Summary & Control Taxonomy

This document provides the definitive, reconciled security control matrix for the BIOS platform. The counting ambiguity identified in Milestone 5.5.3.1 (where 11 N-entries were reported) has been resolved by properly categorizing the AI Agent authorization restriction as a sub-control of **N3 (Self-Approval Prohibition)**, preserving the canonical structure of **10 Negative Controls (N1–N10)** and **2 Positive Controls (C1–C2)**, for a total of 12 controls.

Following the engineering implementation of **Live Owner Verification (Priority 1)** and **Synchronous Expiration Enforcement (Priority 2)**, all 12 controls are classified as **IMPLEMENTED AND TESTED** in application logic without reliance on mock enforcement.

---

## 2. Reconciled Security Control Evidence Matrix (N1–N10, C1–C2)

| Control | Requirement | Implementation location | Enforcement boundary | Test evidence | Audit logging | Status |
|---|---|---|---|---|---|---|
| **N1** | Unapproved Asset Retirement Veto | `backend/app/approvals/service.py` (`approve_request`) | Server-side role authority check (`role_manager.can_review`). Rejects retirement if actor lacks `BI_GOVERNANCE_REVIEWER` role. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n1_unapproved_retirement_blocked` | Yes: Emits `TRANSITION_REJECTED` and `UNAUTHORIZED_APPROVAL_ATTEMPT` | **IMPLEMENTED AND TESTED** |
| **N2** | Retirement Without Evidence / Active Blockers Veto | `backend/app/approvals/service.py`<br>`backend/app/approvals/state_machine.py` | State machine transition validator & blocker detector. Rejects approval if active downstream dependencies or unresolved rule blockers exist. | `backend/tests/test_approvals_rbac.py`<br>`test_hard_governance_blockers_prevent_approval` | Yes: Emits `GOVERNANCE_BLOCKER_VETO` | **IMPLEMENTED AND TESTED** |
| **N3** | Self-Approval Prohibition | `backend/app/approvals/roles.py` (`can_review`) | Direct identity equality check (`actor_id == requester_id`). Requester cannot approve their own lifecycle change request. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n3_self_approval_prohibited`<br>`backend/tests/test_approvals_rbac.py` | Yes: Logged prior to rejection | **IMPLEMENTED AND TESTED** |
| **N3-AI** *(Sub)* | AI Agent Authorization Ban | `backend/app/approvals/roles.py` (`can_review`) | Pattern rejection for agent/bot actors in approval execution. Prevents autonomous AI self-authorization of changes. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n3_ai_agent_self_approval_banned` | Yes: Emits `UNAUTHORIZED_APPROVAL_ATTEMPT` | **IMPLEMENTED AND TESTED** |
| **N4** | Live Inactive-Owner Database Verification | `backend/app/approvals/service.py` (`_verify_live_owner_authority`)<br>`backend/app/approvals/roles.py` | Server-authoritative re-query of `Owners` table at execution time. Rejects inactive owners, forged identities, and asset ownership scope mismatches. | `backend/tests/test_reliability_n4_n5.py`<br>`test_n4_active_owner_can_approve_valid_request`<br>`test_n4_inactive_owner_cannot_approve`<br>`test_n4_owner_becomes_inactive_after_creation_before_approval`<br>`test_n4_missing_or_forged_owner_identity_rejected`<br>`test_n4_owner_scope_mismatch_rejected` | Yes: Emits `UNAUTHORIZED_INACTIVE_OWNER`, `UNAUTHORIZED_OWNER_ACTION`, `OWNER_SCOPE_MISMATCH` | **IMPLEMENTED AND TESTED** |
| **N5** | Synchronous Expired-Waiver Enforcement | `backend/app/approvals/service.py` (`verify_waiver_synchronous` & `approve_request`)<br>`backend/app/artifacts/service.py` | Server-authoritative, timezone-aware UTC comparison at point of use. Rejects expired waivers even if database status is stale `APPROVED`/`ACTIVE`. | `backend/tests/test_reliability_n4_n5.py`<br>`test_n5_valid_active_waiver_accepted`<br>`test_n5_expired_waiver_rejected_synchronously`<br>`test_n5_approval_request_expired_before_decision_rejected`<br>`test_n5_revoked_or_rejected_waiver_rejected`<br>`test_n5_out_of_scope_waiver_rejected`<br>`test_n5_artifact_factory_synchronous_expiry_check` | Yes: Emits `EXPIRED_WAIVER_USE_REJECTED`, `EXPIRED_APPROVAL_ATTEMPT`, `INVALID_WAIVER_STATUS_VETO`, `OUT_OF_SCOPE_WAIVER_VETO` | **IMPLEMENTED AND TESTED** |
| **N6** | RULE-008 Waiver Strictly Prohibited | `backend/app/approvals/service.py` (`verify_waiver_synchronous`)<br>`backend/app/approvals/schemas.py` | Hard validation guard in waiver service and request schema. Prevents creation or application of waivers for RULE-008 (Explainability). | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n6_rule_008_waiver_prohibited`<br>`backend/tests/test_reliability_n4_n5.py`<br>`test_n5_rule_008_waiver_bypass_strictly_prohibited` | Yes: Emits `RULE_008_WAIVER_ATTEMPT_VETO` | **IMPLEMENTED AND TESTED** |
| **N7** | Direct Merge / Build Without Approval Veto | `backend/app/artifacts/service.py` (`generate_artifact`) | Relational lookup against `approval_requests`. Rejects `BUILD_NEW` dashboard artifact creation unless human approval exists and is approved. | `backend/tests/test_artifact_reuse_gate.py`<br>`test_build_new_requires_approval` | Yes: Emits `ARTIFACT_GENERATION_BLOCKED` | **IMPLEMENTED AND TESTED** |
| **N8** | New Build Without Logged RULE-001 Discovery | `backend/app/artifacts/service.py` (`generate_artifact`) | Verifies request ID or specification references valid discovery trace in `assistant_requests`. Direct ungrounded builds are rejected. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n8_new_build_without_logged_rule_001_discovery_blocked` | Yes: Emits `INVALID_SPEC_REQUEST` | **IMPLEMENTED AND TESTED** |
| **N9** | Audit Immutability & Append-Only Log | `backend/app/approvals/audit.py`<br>`backend/app/models/approval.py` (`AuditEvents`) | ORM append-only schema design. Zero update/delete API routes exposed; each lifecycle action appends a complete before/after state record. | `backend/tests/test_audit_immutability.py`<br>`test_audit_log_appended_on_lifecycle_events`<br>`backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_n9_audit_immutability` | Yes: Foundation of all audit logging (`AuditEvents` table) | **IMPLEMENTED AND TESTED** |
| **N10** | Out-of-Allowlist Tool Execution / System Command Injection | `backend/app/agents/orchestrator.py`<br>`backend/tests/benchmarks/test_hallucination_security.py` | Prompt injection firewall; specialist agents execute purely within isolated Python function scopes and Pydantic schemas; zero shell eval. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_prompt_injection_cannot_force_build_new`<br>`test_prompt_injection_cannot_reveal_system_prompt_or_bypass_approval` | Yes: Logged in `AgentExecutionTraces` | **IMPLEMENTED AND TESTED** |
| **C1** | Authorized Evidenced Approval Execution | `backend/app/approvals/service.py` (`approve_request`) | Validates complete chain: reviewer role match + valid evidence snapshot + zero blockers + state transition rules satisfied. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_c1_authorized_evidenced_approval_succeeds` | Yes: Emits `APPROVAL_GRANTED` | **IMPLEMENTED AND TESTED** |
| **C2** | Valid Standard Action Authority Execution | `backend/app/approvals/roles.py` (`can_review`) | Verifies designated reviewer operates cleanly within mapped action authority hierarchy. | `backend/tests/benchmarks/test_hallucination_security.py`<br>`test_security_c2_valid_standard_action_succeeds` | Yes: Audit records authorized execution | **IMPLEMENTED AND TESTED** |

---

## 3. Summary of Reconciled Counts

- **Total Original Negative Controls**: 10 (N1 through N10)
  - *Note*: N3-AI is formally classified as a sub-rule of N3 (Self-Approval Prohibition), maintaining strict alignment with original specifications.
- **Total Original Positive Controls**: 2 (C1 and C2)
- **Total Canonical Controls**: **12**
- **Implemented and Tested in Application Logic**: **12 (100.0%)**
- **Partially Implemented**: **0 (0.0%)**
- **Tested Only Through Mocks**: **0 (0.0%)**
- **Not Implemented**: **0 (0.0%)**
- **Not Verified**: **0 (0.0%)**

---

## 4. Auditor Sign-Off

The security enforcement boundaries for BIOS Milestone 5.6 have been verified directly in application logic. All negative controls (rejection of unauthorized, unevidenced, stale, expired, out-of-scope, or unapproved actions) and positive controls (authorized evidenced progressions) pass automated test execution with zero regressions across the 410-test suite.

