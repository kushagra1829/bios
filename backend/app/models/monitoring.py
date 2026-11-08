from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class MonitoringExecutionRuns(Base):
    """
    Audit log of continuous governance monitoring jobs.
    Tracks execution status, timing, processed entities, and generated governance signals.
    """
    __tablename__ = "monitoring_execution_runs"

    job_id = Column(String(64), primary_key=True)
    job_type = Column(String(50), nullable=False, index=True)
    # 'CATALOG_SYNC', 'GOVERNANCE_REEVAL', 'DUPLICATE_DETECTION', 'KPI_CONSISTENCY',
    # 'OWNERSHIP_AUDIT', 'LINEAGE_VALIDATION', 'SEMANTIC_READINESS', 'LIFECYCLE_REEVAL', 'FULL_CONTINUOUS_SCAN'
    status = Column(String(30), nullable=False, default="RUNNING", index=True)  # 'RUNNING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    records_processed = Column(Integer, nullable=False, default=0)
    findings_generated = Column(Integer, nullable=False, default=0)
    findings_resolved = Column(Integer, nullable=False, default=0)
    errors = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    source_connector = Column(String(50), nullable=True)  # 'Power BI', 'Tableau', 'INTERNAL', 'ALL'
    details_json = Column(Text, nullable=True)


class GovernanceAlerts(Base):
    """
    Enterprise alert center records derived from deterministic governance findings.
    Provides acknowledgement, assignment, and remediation tracking without clearing underlying findings.
    """
    __tablename__ = "governance_alerts"

    alert_id = Column(String(64), primary_key=True)
    finding_id = Column(String(64), ForeignKey("governance_findings.finding_id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String(20), nullable=False, index=True)
    target_entity_type = Column(String(50), nullable=False)
    target_entity_id = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # 'critical', 'high', 'medium', 'low'
    status = Column(String(30), nullable=False, default="NEW", index=True)  # 'NEW', 'ACKNOWLEDGED', 'RESOLVED'
    title = Column(String(255), nullable=False)
    explanation = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledgement_rationale = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    finding = relationship("GovernanceFindings")

