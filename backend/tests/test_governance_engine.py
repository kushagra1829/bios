import pytest
from backend.app.db.session import SessionLocal
from backend.app.governance.engine import GovernanceEngine
from backend.app.governance.evidence import compute_finding_id
from backend.app.governance.schemas import RuleId, FindingStatus
from backend.app.models.governance import GovernanceEvaluationRuns, GovernanceFindings


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_finding_id_determinism():
    id1 = compute_finding_id("RULE-001", "asset", "AST-0001", "waste_reduction")
    id2 = compute_finding_id("RULE-001", "asset", "AST-0001", "waste_reduction")
    id3 = compute_finding_id("RULE-002", "asset", "AST-0001", "waste_reduction")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("FND-RULE001-")


def test_governance_engine_evaluation_run(db):
    engine = GovernanceEngine()
    summary = engine.evaluate_all(db)

    assert summary.status == "success"
    assert summary.run_id.startswith("RUN-")
    assert summary.total_findings > 0
    assert summary.execution_time_ms > 0

    # Verify run persisted in database
    run_record = db.query(GovernanceEvaluationRuns).filter(GovernanceEvaluationRuns.run_id == summary.run_id).first()
    assert run_record is not None
    assert run_record.status == "success"
    assert run_record.total_findings == summary.total_findings


def test_governance_engine_lifecycle_persisting(db):
    engine = GovernanceEngine()

    # First run creates or updates
    run1 = engine.evaluate_all(db)
    assert run1.status == "success"

    # Second run should transition or keep all active findings in 'persisting' status
    run2 = engine.evaluate_all(db)
    assert run2.status == "success"
    assert run2.findings_by_status.get(FindingStatus.PERSISTING.value, 0) > 0


def test_governance_engine_evaluate_single_rule(db):
    engine = GovernanceEngine()
    findings = engine.evaluate_rule(RuleId.RULE_003, db)
    assert len(findings) > 0
    for f in findings:
        assert f.rule_id == RuleId.RULE_003


def test_governance_engine_get_summary(db):
    engine = GovernanceEngine()
    summary = engine.get_summary(db)

    assert "total_active_findings" in summary
    assert "findings_by_severity" in summary
    assert "findings_by_rule" in summary
    assert "latest_run" in summary
    assert summary["total_active_findings"] > 0

