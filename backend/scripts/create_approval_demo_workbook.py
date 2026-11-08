"""
Script to create bios_approval_demo_dataset.xlsx containing the four sheets:
- Approval_Requests
- Approval_Evidence
- Demo_Actors
- README
"""
from pathlib import Path
import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK_PATH = REPO_ROOT / "bios_approval_demo_dataset.xlsx"

APPROVAL_REQUESTS = [
    ("approval_id", "requester_id", "target_entity_id", "action_type", "required_role", "recommendation_ref", "submitted_at_utc", "status", "title", "requester_rationale", "decided_by", "decided_at_utc", "decision_rationale"),
    ("DEMO-APP-001", "REQ-001", "AST-0024", "REUSE", "ASSET_OWNER", "REQ-DEMO-101", "2026-11-06T09:15:00Z", "PENDING", "Reuse certified Nubeqa sales report for France", "Verify KPI coverage and lifecycle eligibility.", "", "", ""),
    ("DEMO-APP-002", "REQ-001", "AST-0068", "MODIFY", "ASSET_OWNER", "REQ-DEMO-102", "2026-11-06T10:30:00Z", "PENDING", "Add forecast variance to the Nubeqa portfolio report", "Owner review required for the governed measure change.", "", "", ""),
    ("DEMO-APP-003", "analyst_maria", "AST-0014", "CONSOLIDATE", "ASSET_OWNER", "REQ-DEMO-103", "2026-11-06T11:05:00Z", "PENDING", "Consolidate duplicate regional sales views", "Validate KPI equivalence, audience, lineage and dependencies.", "", "", ""),
    ("DEMO-APP-004", "REQ-USER-1", "AST-0028", "RETIRE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-104", "2026-11-06T13:20:00Z", "PENDING", "Retire an unused legacy report", "Confirm no critical downstream dependencies or active consumers.", "", "", ""),
    ("DEMO-APP-005", "analyst_john", "AST-0031", "BUILD_NEW", "DOMAIN_STEWARD", "REQ-DEMO-105", "2026-11-06T14:10:00Z", "PENDING", "Create a new market access dashboard", "Validate canonical KPI selection and semantic model readiness.", "", "", ""),
    ("DEMO-APP-006", "REQ-001", "AST-0042", "MODIFY", "ASSET_OWNER", "REQ-DEMO-106", "2026-11-05T08:45:00Z", "APPROVED", "Add a market filter to the existing report", "No certified KPI definition change.", "OWN-001", "2026-11-05T10:12:00Z", "Approved after scope and impact review."),
    ("DEMO-APP-007", "analyst_erin", "AST-0055", "REUSE", "ASSET_OWNER", "REQ-DEMO-107", "2026-11-05T09:30:00Z", "APPROVED", "Reuse the existing supply dashboard", "Asset and audience fit confirmed in this illustrative example.", "OWN-001", "2026-11-05T11:00:00Z", "Approved after asset and KPI review."),
    ("DEMO-APP-008", "REQ-USER-1", "AST-0072", "CONSOLIDATE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-108", "2026-11-04T12:00:00Z", "REJECTED", "Consolidate reports with conflicting KPI definitions", "Incompatible KPI definitions; no approved mapping supplied.", "REV-001", "2026-11-04T15:20:00Z", "Rejected: canonical KPI conflict remains unresolved."),
    ("DEMO-APP-009", "analyst_maria", "AST-0081", "RETIRE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-109", "2026-11-04T14:25:00Z", "CHANGES_REQUESTED", "Retire a legacy regional report", "Lineage and owner confirmation are incomplete.", "REV-001", "2026-11-04T16:05:00Z", "Provide lineage evidence and confirm active consumers."),
    ("DEMO-APP-010", "analyst_john", "AST-0093", "MODIFY", "ASSET_OWNER", "REQ-DEMO-110", "2026-11-03T09:40:00Z", "PENDING", "Update the reporting period on a sales report", "Confirm time-intelligence and historical comparability impact.", "", "", ""),
    ("DEMO-APP-011", "REQ-001", "AST-0107", "REUSE", "ASSET_OWNER", "REQ-DEMO-111", "2026-11-03T10:10:00Z", "PENDING", "Reuse an endorsed commercial performance report", "Verify active lifecycle and requested measure coverage.", "", "", ""),
    ("DEMO-APP-012", "analyst_erin", "AST-0118", "BUILD_NEW", "DOMAIN_STEWARD", "REQ-DEMO-112", "2026-11-03T13:35:00Z", "PENDING", "Build a new regional access dashboard", "Domain review of semantic model and canonical KPIs required.", "", "", ""),
    ("DEMO-APP-013", "REQ-USER-1", "AST-0130", "MODIFY", "ASSET_OWNER", "REQ-DEMO-113", "2026-11-02T08:20:00Z", "APPROVED", "Add a certified KPI to an existing report", "Owner confirmed KPI mapping and asset scope.", "OWN-001", "2026-11-02T10:00:00Z", "Approved with verified KPI mapping."),
    ("DEMO-APP-014", "analyst_maria", "AST-0142", "CONSOLIDATE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-114", "2026-11-02T11:45:00Z", "REJECTED", "Consolidate two high-reach reports", "Audience and downstream dependencies differ materially.", "REV-001", "2026-11-02T14:30:00Z", "Rejected due to audience and dependency differences."),
    ("DEMO-APP-015", "analyst_john", "AST-0157", "REUSE", "ASSET_OWNER", "REQ-DEMO-115", "2026-11-01T09:00:00Z", "CHANGES_REQUESTED", "Reuse an existing sales report", "Sales KPI coverage is not demonstrated; evidence is required.", "OWN-001", "2026-11-01T11:15:00Z", "Provide canonical KPI coverage evidence before reuse."),
    ("DEMO-APP-016", "REQ-001", "AST-0168", "RETIRE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-116", "2026-10-31T10:05:00Z", "PENDING", "Retire a duplicate legacy dashboard", "Current owner confirmation and downstream lineage evidence required.", "", "", ""),
    ("DEMO-APP-017", "analyst_erin", "AST-0180", "MODIFY", "ASSET_OWNER", "REQ-DEMO-117", "2026-10-30T12:40:00Z", "APPROVED", "Update report title and description", "Metadata-only change; no semantic or audience impact.", "OWN-001", "2026-10-30T14:00:00Z", "Approved as a metadata-only change."),
    ("DEMO-APP-018", "REQ-USER-1", "AST-0194", "BUILD_NEW", "DOMAIN_STEWARD", "REQ-DEMO-118", "2026-10-29T15:15:00Z", "CHANGES_REQUESTED", "Create a new executive dashboard", "Business purpose, audience and KPI selection need clarification.", "OWN-003", "2026-10-30T09:10:00Z", "Provide audience definition and KPI specification."),
    ("DEMO-APP-019", "analyst_maria", "AST-0210", "CONSOLIDATE", "BI_GOVERNANCE_REVIEWER", "REQ-DEMO-119", "2026-10-28T08:50:00Z", "PENDING", "Consolidate overlapping market reports", "Verify equivalent KPI formulas and lineage before approval.", "", "", ""),
    ("DEMO-APP-020", "analyst_john", "AST-0222", "MODIFY", "ASSET_OWNER", "REQ-DEMO-120", "2026-10-27T10:25:00Z", "PENDING", "Modify an existing forecast report", "Confirm forecast horizon and approved variance calculation.", "", "", ""),
]

APPROVAL_EVIDENCE = [
    ("approval_id", "evidence_type", "evidence_item", "evidence_summary", "evidence_status"),
    ("DEMO-APP-001", "KPI_COVERAGE", "Net Sales", "Verify against target asset KPI map", "REQUIRES_REVIEW"),
    ("DEMO-APP-001", "LIFECYCLE", "Candidate lifecycle", "Confirm target is active and not candidate-retire", "REQUIRES_REVIEW"),
    ("DEMO-APP-002", "CHANGE_SCOPE", "Forecast variance", "Owner validates measure definition and impact", "REQUIRES_REVIEW"),
    ("DEMO-APP-003", "DUPLICATION", "Potential overlap", "Compare KPI formulas, audience and lineage", "REQUIRES_REVIEW"),
    ("DEMO-APP-004", "USAGE", "Low recent usage", "Confirm no critical downstream dependencies", "REQUIRES_REVIEW"),
    ("DEMO-APP-005", "SEMANTIC_READINESS", "New model required", "Validate canonical KPIs and model readiness", "REQUIRES_REVIEW"),
    ("DEMO-APP-008", "KPI_CONFLICT", "Conflicting KPI definitions", "Unresolved canonical definition conflict", "BLOCKER"),
    ("DEMO-APP-009", "LINEAGE", "Incomplete dependency evidence", "Lineage confirmation required", "BLOCKER"),
    ("DEMO-APP-015", "KPI_COVERAGE", "Sales KPI not demonstrated", "Reuse requires coverage evidence", "BLOCKER"),
]

DEMO_ACTORS = [
    ("actor_id", "display_name", "role", "scope_label"),
    ("REQ-001", "Requester / Business Analyst", "REQUESTER", "Individual Business Scope"),
    ("analyst_maria", "Maria (Demo Analyst)", "REQUESTER", "Individual Business Scope"),
    ("analyst_john", "John (Demo Analyst)", "REQUESTER", "Individual Business Scope"),
    ("analyst_erin", "Erin (Demo Analyst)", "REQUESTER", "Individual Business Scope"),
    ("OWN-001", "Nina Garcia", "ASSET_OWNER", "Assigned Assets"),
    ("OWN-003", "Maya Andersson", "DOMAIN_STEWARD", "Domain Scope"),
    ("REV-001", "BI Governance Reviewer", "BI_GOVERNANCE_REVIEWER", "Enterprise Scope"),
]

README_ROWS = [
    ("item", "description"),
    ("Purpose", "Synthetic demo rows for the BIOS Approvals & Human Adjudication page."),
    ("Provenance", "Illustrative sample records only; not actual Bayer decisions, approvals, business data or production identities."),
    ("Integration", "Inspect existing SQLAlchemy approval models and API contracts before mapping these columns. This workbook is a staging dataset, not a guaranteed schema match."),
    ("Security", "Never grant authority from this workbook. Resolve identity, active owner status, required role, target scope and anti-self-approval through existing backend authorization."),
    ("Statuses", "Includes PENDING, APPROVED, REJECTED and CHANGES_REQUESTED examples."),
    ("IDs", "DEMO-APP-* and REQ-DEMO-* are reserved demo IDs. Check collisions before seeding."),
    ("Seeding", "Seed only into a clearly marked local/demo database. Make import idempotent and reversible."),
]


def create_workbook():
    wb = openpyxl.Workbook()
    # Sheet 1: Approval_Requests
    ws1 = wb.active
    ws1.title = "Approval_Requests"
    for row in APPROVAL_REQUESTS:
        ws1.append(row)

    # Sheet 2: Approval_Evidence
    ws2 = wb.create_sheet(title="Approval_Evidence")
    for row in APPROVAL_EVIDENCE:
        ws2.append(row)

    # Sheet 3: Demo_Actors
    ws3 = wb.create_sheet(title="Demo_Actors")
    for row in DEMO_ACTORS:
        ws3.append(row)

    # Sheet 4: README
    ws4 = wb.create_sheet(title="README")
    for row in README_ROWS:
        ws4.append(row)

    wb.save(WORKBOOK_PATH)
    print(f"Created {WORKBOOK_PATH} with 4 sheets successfully.")


if __name__ == "__main__":
    create_workbook()

