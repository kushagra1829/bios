import hashlib
import json
from typing import Any, Dict, List, Optional
from backend.app.governance.schemas import EvidenceReference, EvidenceBundle


def create_evidence_reference(
    source_table: str,
    record_id: str,
    field_name: str,
    observed_value: Any,
    expected_condition: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> EvidenceReference:
    return EvidenceReference(
        source_table=source_table,
        record_id=str(record_id),
        field_name=field_name,
        observed_value=observed_value,
        expected_condition=expected_condition,
        metadata=metadata or {},
    )


def create_evidence_bundle(
    primary_reference: EvidenceReference,
    corroborating_references: Optional[List[EvidenceReference]] = None,
    context_notes: Optional[str] = None,
    verified: bool = True,
) -> EvidenceBundle:
    return EvidenceBundle(
        primary_reference=primary_reference,
        corroborating_references=corroborating_references or [],
        context_notes=context_notes,
        verified=verified,
    )


def compute_finding_id(rule_id: str, entity_type: str, entity_id: str, category: str) -> str:
    """Deterministic, reproducible unique finding identifier."""
    raw = f"{rule_id}:{entity_type}:{entity_id}:{category}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"FND-{rule_id.replace('-', '')}-{digest.upper()}"

