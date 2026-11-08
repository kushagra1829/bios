import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import Base, engine, SessionLocal
from backend.app.monitoring.engine import continuous_monitoring_engine
from backend.app.models.monitoring import MonitoringExecutionRuns, GovernanceAlerts
from backend.app.models.governance import GovernanceFindings


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_continuous_monitoring_full_scan(db_session):
    """Verify continuous monitoring engine executes all phases of full scan."""
    job = continuous_monitoring_engine.run_monitoring_job(
        db=db_session,
        job_type="FULL_CONTINUOUS_SCAN",
        triggered_by="TEST_SUITE",
    )
    assert job.job_id.startswith("JOB-")
    assert job.status in ("SUCCESS", "PARTIAL_SUCCESS")
    assert job.records_processed >= 0
    assert job.duration_ms >= 0


def test_concurrent_execution_protection(db_session):
    """Verify engine blocks concurrent execution of identical running job types."""
    # Seed a RUNNING job
    fake_running_job = MonitoringExecutionRuns(
        job_id="JOB-LOCK-TEST",
        job_type="GOVERNANCE_REEVAL",
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(fake_running_job)
    db_session.commit()

    try:
        # Attempt concurrent run
        second_job = continuous_monitoring_engine.run_monitoring_job(
            db=db_session,
            job_type="GOVERNANCE_REEVAL",
            triggered_by="TEST_CONCURRENT",
        )
        assert second_job.status == "FAILED"
        assert "Concurrent execution blocked" in second_job.errors
    finally:
        db_session.delete(fake_running_job)
        db_session.commit()


def test_alerts_generated_from_findings(db_session):
    """Verify critical and high findings generate alerts in GovernanceAlerts."""
    alerts = db_session.query(GovernanceAlerts).all()
    assert len(alerts) > 0

    first_alert = alerts[0]
    assert first_alert.alert_id.startswith("ALT-")
    assert first_alert.severity in ("critical", "high")
    assert first_alert.status in ("NEW", "ACKNOWLEDGED", "RESOLVED")


def test_alert_acknowledgement_does_not_clear_violation(client, db_session):
    """
    INVARIANT CHECK:
    Acknowledging an alert must NOT silently resolve or clear the underlying governance finding.
    The finding remains active, while the alert records user acknowledgement.
    """
    # Find a NEW alert
    alert = db_session.query(GovernanceAlerts).filter(GovernanceAlerts.status == "NEW").first()
    if not alert:
        # Trigger scan to generate alerts
        continuous_monitoring_engine.run_monitoring_job(db=db_session, job_type="GOVERNANCE_REEVAL")
        alert = db_session.query(GovernanceAlerts).filter(GovernanceAlerts.status == "NEW").first()

    assert alert is not None
    alert_id = alert.alert_id
    finding_id = alert.finding_id

    # 1. Verify underlying finding is open/persisting before acknowledgement
    finding_before = db_session.query(GovernanceFindings).filter(GovernanceFindings.finding_id == finding_id).first()
    assert finding_before is not None
    assert finding_before.status in ("open", "persisting")

    # 2. Acknowledge alert via API with valid rationale
    ack_payload = {
        "actor_id": "OWN-001",
        "actor_role": "BI Governance Reviewer",
        "rationale": "Acknowledged risk; remediation scheduled in upcoming sprint backlog.",
    }
    resp = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", json=ack_payload)
    assert resp.status_code == 200
    ack_data = resp.json()
    assert ack_data["status"] == "ACKNOWLEDGED"
    assert "OWN-001" in ack_data["acknowledged_by"]

    # 3. CRITICAL INVARIANT: Verify underlying finding is STILL open/persisting!
    db_session.expire_all()
    finding_after = db_session.query(GovernanceFindings).filter(GovernanceFindings.finding_id == finding_id).first()
    assert finding_after.status in ("open", "persisting"), "Violation: Acknowledging an alert silently resolved the finding!"


def test_alert_acknowledgement_rationale_validation(client):
    """Verify acknowledgement is rejected if rationale is shorter than 5 chars."""
    resp = client.post(
        "/api/v1/alerts/ALT-NONEXISTENT/acknowledge",
        json={"actor_id": "OWN-001", "actor_role": "Reviewer", "rationale": "abc"},
    )
    assert resp.status_code == 422  # Validation error on min_length=5


def test_monitoring_api_endpoints(client):
    """Verify monitoring summary and jobs listing endpoints."""
    # Summary
    resp_sum = client.get("/api/v1/monitoring/summary")
    assert resp_sum.status_code == 200
    data_sum = resp_sum.json()
    assert data_sum["monitoring_active"] is True
    assert "total_jobs_executed" in data_sum

    # Jobs
    resp_jobs = client.get("/api/v1/monitoring/jobs?limit=10")
    assert resp_jobs.status_code == 200
    jobs = resp_jobs.json()
    assert isinstance(jobs, list)


def test_alerts_api_endpoints(client):
    """Verify alerts listing and summary endpoints."""
    resp_sum = client.get("/api/v1/alerts/summary")
    assert resp_sum.status_code == 200
    sum_data = resp_sum.json()
    assert "total_active_alerts" in sum_data
    assert "by_severity" in sum_data

    resp_list = client.get("/api/v1/alerts?limit=20")
    assert resp_list.status_code == 200
    alerts = resp_list.json()
    assert isinstance(alerts, list)

