import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.models.approval import AuditEvents

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Append-only, immutable audit logging service for BIOS.
    Ensures that every consequential human decision, approval state transition,
    and governance event is permanently recorded with full before/after snapshots.
    """

    @classmethod
    def record_event(
        cls,
        db: Session,
        actor_id: str,
        actor_role: str,
        event_type: str,
        target_entity_type: str,
        target_entity_id: str,
        action: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        evidence_snapshot: Optional[Dict[str, Any]] = None,
        associated_recommendation_id: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> AuditEvents:
        """
        Append an immutable audit record to the audit_events table.
        """
        event_id = f"AUD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        event = AuditEvents(
            event_id=event_id,
            actor_id=actor_id,
            actor_role=actor_role,
            event_type=event_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            action=action,
            before_state_json=json.dumps(before_state) if before_state else None,
            after_state_json=json.dumps(after_state) if after_state else None,
            reason=reason,
            evidence_snapshot_json=json.dumps(evidence_snapshot) if evidence_snapshot else None,
            associated_recommendation_id=associated_recommendation_id,
            provenance_json=json.dumps(provenance) if provenance else None,
            created_at=datetime.now(timezone.utc),
        )

        db.add(event)
        db.flush()
        logger.info(
            f"[AuditLogger] Appended event {event_id}: actor='{actor_id}' ({actor_role}), "
            f"action='{action}', target='{target_entity_type}:{target_entity_id}'"
        )
        return event


audit_logger = AuditLogger()

