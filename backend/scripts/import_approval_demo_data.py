"""
Idempotent importer and management script for BIOS Approval Demo Dataset.
Reads bios_approval_demo_dataset.xlsx, validates asset references and roles,
and seeds ApprovalRequests, ApprovalStateTransitions, and AuditEvents.

Supports:
  --clean / --rollback: Safely removes only records with DEMO-APP-* identifiers.
  --verify: Inspects and prints summary of demo records in the database.
"""
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import openpyxl
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db.session import SessionLocal
from backend.app.models.approval import (
    ApprovalRequests,
    ApprovalStateTransitions,
    AuditEvents,
)
from backend.app.models.core import AnalyticsAssets, Owners

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKBOOK = REPO_ROOT / "bios_approval_demo_dataset.xlsx"


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str or not str(dt_str).strip():
        return None
    s = str(dt_str).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def clean_demo_data(db) -> int:
    """Safely remove only records introduced by this demo import (DEMO-APP-*)."""
    demo_requests = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id.like("DEMO-APP-%")).all()
    count = len(demo_requests)
    if count == 0:
        logger.info("No DEMO-APP-* records found to clean.")
        return 0

    demo_ids = [r.approval_id for r in demo_requests]

    # Delete transitions
    db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.approval_id.in_(demo_ids)).delete(synchronize_session=False)

    # Delete audit events associated with demo approvals or recommendations
    db.query(AuditEvents).filter(
        (AuditEvents.target_entity_id.in_(demo_ids)) |
        (AuditEvents.action.like("%DEMO-APP-%")) |
        (AuditEvents.associated_recommendation_id.like("REQ-DEMO-%"))
    ).delete(synchronize_session=False)

    # Delete approvals
    db.query(ApprovalRequests).filter(ApprovalRequests.approval_id.in_(demo_ids)).delete(synchronize_session=False)

    db.commit()
    logger.info(f"Cleaned {count} DEMO-APP-* approval records and associated transitions/audit events.")
    return count


def import_demo_data(workbook_path: Path, db) -> Dict[str, Any]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook not found at {workbook_path}")

    wb = openpyxl.load_workbook(workbook_path, data_only=True)

    # 1. Load Evidence Sheet
    evidence_by_app_id: Dict[str, List[Dict[str, Any]]] = {}
    if "Approval_Evidence" in wb.sheetnames:
        ws_ev = wb["Approval_Evidence"]
        ev_rows = list(ws_ev.iter_rows(values_only=True))
        if len(ev_rows) > 1:
            header = [str(c).strip() if c else "" for c in ev_rows[0]]
            for r in ev_rows[1:]:
                if not r or not r[0]:
                    continue
                row_dict = dict(zip(header, r))
                app_id = str(row_dict.get("approval_id", "")).strip()
                if app_id:
                    evidence_by_app_id.setdefault(app_id, []).append(row_dict)

    # 2. Load Actors Sheet
    actors_by_id: Dict[str, Dict[str, Any]] = {}
    if "Demo_Actors" in wb.sheetnames:
        ws_act = wb["Demo_Actors"]
        act_rows = list(ws_act.iter_rows(values_only=True))
        if len(act_rows) > 1:
            header = [str(c).strip() if c else "" for c in act_rows[0]]
            for r in act_rows[1:]:
                if not r or not r[0]:
                    continue
                row_dict = dict(zip(header, r))
                act_id = str(row_dict.get("actor_id", "")).strip()
                if act_id:
                    actors_by_id[act_id] = row_dict

    # 3. Load Approval Requests
    if "Approval_Requests" not in wb.sheetnames:
        raise ValueError("Sheet 'Approval_Requests' missing from workbook.")

    ws_req = wb["Approval_Requests"]
    req_rows = list(ws_req.iter_rows(values_only=True))
    if len(req_rows) <= 1:
        logger.warning("No data rows found in Approval_Requests sheet.")
        return {"imported": 0, "updated": 0, "skipped": 0, "statuses": {}}

    header = [str(c).strip() if c else "" for c in req_rows[0]]

    stats = {"imported": 0, "updated": 0, "skipped": 0, "statuses": {}}

    for r in req_rows[1:]:
        if not r or not r[0]:
            continue
        row = dict(zip(header, r))
        approval_id = str(row["approval_id"]).strip()
        requester_id = str(row["requester_id"]).strip()
        target_entity_id = str(row["target_entity_id"]).strip()
        action_type = str(row["action_type"]).strip().upper()
        required_role = str(row["required_role"]).strip().upper()
        recommendation_ref = str(row.get("recommendation_ref", "") or "").strip() or None
        submitted_at = parse_datetime(row.get("submitted_at_utc")) or datetime.now(timezone.utc)
        status_val = str(row["status"]).strip().upper()
        title = str(row["title"]).strip()
        requester_rationale = str(row.get("requester_rationale", "") or "").strip()
        decided_by = str(row.get("decided_by", "") or "").strip() or None
        decided_at = parse_datetime(row.get("decided_at_utc"))
        decision_rationale = str(row.get("decision_rationale", "") or "").strip() or None

        # Validation: check target entity exists in AnalyticsAssets
        asset = db.query(AnalyticsAssets).filter(AnalyticsAssets.asset_id == target_entity_id).first()
        if not asset:
            logger.warning(f"Target entity {target_entity_id} does not exist in AnalyticsAssets catalog! Proceeding with caution.")

        # Process evidence
        ev_items = evidence_by_app_id.get(approval_id, [])
        blockers = []
        warnings = []
        for ev in ev_items:
            ev_status = str(ev.get("evidence_status", "")).strip().upper()
            summary = f"{ev.get('evidence_type', '')}: {ev.get('evidence_summary', '') or ev.get('evidence_item', '')}"
            if ev_status == "BLOCKER":
                blockers.append(summary)
            else:
                warnings.append(summary)

        evidence_json = json.dumps(ev_items) if ev_items else json.dumps({"note": "Standard portfolio review"})
        blockers_json = json.dumps(blockers)
        warnings_json = json.dumps(warnings)

        # Decide actor role for decided_by
        decided_role = None
        if decided_by:
            if decided_by in actors_by_id:
                decided_role = actors_by_id[decided_by].get("role")
            elif decided_by.startswith("OWN-"):
                decided_role = "ASSET_OWNER"
            elif decided_by.startswith("REV-"):
                decided_role = "BI_GOVERNANCE_REVIEWER"
            elif decided_by.startswith("ADM-"):
                decided_role = "BIOS_ADMIN"

        # Check existing
        existing = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id == approval_id).first()

        if existing:
            # Update existing
            existing.target_entity_type = "asset"
            existing.target_entity_id = target_entity_id
            existing.action_type = action_type
            existing.recommendation_ref = recommendation_ref
            existing.requester_id = requester_id
            existing.required_role = required_role
            existing.status = status_val
            existing.title = title
            existing.description = requester_rationale
            existing.evidence_snapshot_json = evidence_json
            existing.blockers_json = blockers_json
            existing.warnings_json = warnings_json
            existing.decided_by_id = decided_by
            existing.decided_by_role = decided_role
            existing.decision_reason = decision_rationale
            existing.decided_at = decided_at
            existing.updated_at = datetime.now(timezone.utc)
            stats["updated"] += 1
        else:
            # Insert new
            app_req = ApprovalRequests(
                approval_id=approval_id,
                target_entity_type="asset",
                target_entity_id=target_entity_id,
                action_type=action_type,
                recommendation_ref=recommendation_ref,
                requester_id=requester_id,
                requester_role="REQUESTER",
                required_role=required_role,
                status=status_val,
                title=title,
                description=requester_rationale,
                evidence_snapshot_json=evidence_json,
                blockers_json=blockers_json,
                warnings_json=warnings_json,
                decision_reason=decision_rationale,
                decided_by_id=decided_by,
                decided_by_role=decided_role,
                decided_at=decided_at,
                created_at=submitted_at,
                updated_at=decided_at or submitted_at,
            )
            db.add(app_req)
            stats["imported"] += 1

        stats["statuses"][status_val] = stats["statuses"].get(status_val, 0) + 1

        # Manage Transitions
        # 1. Initial transition DRAFT -> PENDING
        trn_1_id = f"TRN-{approval_id}-001"
        trn_1 = db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.transition_id == trn_1_id).first()
        if not trn_1:
            trn_1 = ApprovalStateTransitions(
                transition_id=trn_1_id,
                approval_id=approval_id,
                from_state="DRAFT",
                to_state="PENDING",
                actor_id=requester_id,
                actor_role="REQUESTER",
                comment=f"Request submitted: {title}",
                transitioned_at=submitted_at,
            )
            db.add(trn_1)

        # 2. Final transition if decided (APPROVED, REJECTED, CHANGES_REQUESTED)
        if status_val in ("APPROVED", "REJECTED", "CHANGES_REQUESTED") and decided_by:
            trn_2_id = f"TRN-{approval_id}-002"
            trn_2 = db.query(ApprovalStateTransitions).filter(ApprovalStateTransitions.transition_id == trn_2_id).first()
            if not trn_2:
                trn_2 = ApprovalStateTransitions(
                    transition_id=trn_2_id,
                    approval_id=approval_id,
                    from_state="PENDING",
                    to_state=status_val,
                    actor_id=decided_by,
                    actor_role=decided_role or "REVIEWER",
                    comment=decision_rationale or f"Decision executed: {status_val}",
                    transitioned_at=decided_at or submitted_at,
                )
                db.add(trn_2)

        # Audit Events
        # Initial submission audit event
        aud_1_id = f"AUD-{approval_id}-SUB"
        aud_1 = db.query(AuditEvents).filter(AuditEvents.event_id == aud_1_id).first()
        if not aud_1:
            aud_1 = AuditEvents(
                event_id=aud_1_id,
                actor_id=requester_id,
                actor_role="REQUESTER",
                event_type="APPROVAL_REQUESTED",
                target_entity_type="asset",
                target_entity_id=target_entity_id,
                action=f"REQUEST_{action_type}",
                before_state_json=None,
                after_state_json=json.dumps({"status": "PENDING", "required_role": required_role}),
                reason=title,
                evidence_snapshot_json=evidence_json,
                associated_recommendation_id=recommendation_ref,
                created_at=submitted_at,
            )
            db.add(aud_1)

        # Decision audit event
        if status_val in ("APPROVED", "REJECTED", "CHANGES_REQUESTED") and decided_by:
            aud_2_id = f"AUD-{approval_id}-DEC"
            aud_2 = db.query(AuditEvents).filter(AuditEvents.event_id == aud_2_id).first()
            evt_type_map = {
                "APPROVED": "APPROVAL_GRANTED",
                "REJECTED": "APPROVAL_REJECTED",
                "CHANGES_REQUESTED": "CHANGES_REQUESTED",
            }
            if not aud_2:
                aud_2 = AuditEvents(
                    event_id=aud_2_id,
                    actor_id=decided_by,
                    actor_role=decided_role or "REVIEWER",
                    event_type=evt_type_map.get(status_val, "APPROVAL_DECISION"),
                    target_entity_type="asset",
                    target_entity_id=target_entity_id,
                    action=f"{status_val}_{action_type}",
                    before_state_json=json.dumps({"status": "PENDING"}),
                    after_state_json=json.dumps({"status": status_val, "decided_by": decided_by}),
                    reason=decision_rationale or title,
                    evidence_snapshot_json=evidence_json,
                    associated_recommendation_id=recommendation_ref,
                    created_at=decided_at or submitted_at,
                )
                db.add(aud_2)

    db.commit()
    return stats


def verify_demo_data(db):
    demo_requests = db.query(ApprovalRequests).filter(ApprovalRequests.approval_id.like("DEMO-APP-%")).order_by(ApprovalRequests.approval_id.asc()).all()
    print(f"\nTotal DEMO-APP-* Records in Database: {len(demo_requests)}")
    by_status = {}
    by_req = {}
    by_role = {}
    for r in demo_requests:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_req[r.requester_id] = by_req.get(r.requester_id, 0) + 1
        by_role[r.required_role] = by_role.get(r.required_role, 0) + 1

    print("Counts by Status:", by_status)
    print("Counts by Requester:", by_req)
    print("Counts by Required Role:", by_role)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import BIOS Approval Demo Dataset")
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK), help="Path to excel workbook")
    parser.add_argument("--clean", "--rollback", action="store_true", help="Remove all DEMO-APP-* records")
    parser.add_argument("--verify", action="store_true", help="Verify records in database")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.clean:
            clean_demo_data(db)
        else:
            stats = import_demo_data(Path(args.workbook), db)
            print(f"Import complete: {stats}")
            if args.verify or True:
                verify_demo_data(db)
    finally:
        db.close()
