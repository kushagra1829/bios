import pytest
from backend.app.db.session import SessionLocal
from backend.app.lifecycle.scoring import scoring_engine
from backend.app.lifecycle.rules import lifecycle_rules
from backend.app.lifecycle.schemas import LifecycleAction
from backend.app.models.core import AnalyticsAssets


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_veto_downstream_dependencies_block_retirement(db_session):
    # Find or simulate a Power BI asset with downstream dependents
    asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.platform == "Power BI", AnalyticsAssets.lifecycle_status == "candidate_retire")
        .first()
    )
    assert asset is not None

    breakdown, evidence = scoring_engine.calculate_score(asset, db_session)
    # Force downstream dependent count in evidence to 2
    evidence["lineage"]["downstream_dependent_count"] = 2

    action, conf, exp, risks, approval = lifecycle_rules.evaluate_asset(asset, breakdown, evidence)

    # Must be VETOED to REVIEW
    assert action == LifecycleAction.REVIEW
    assert "Retirement VETOED" in exp
    assert any("Lineage Dependency" in r for r in risks)
    assert approval is True


def test_veto_certified_endorsement_blocks_retirement(db_session):
    certified_asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.endorsement == "certified")
        .first()
    )
    assert certified_asset is not None

    breakdown, evidence = scoring_engine.calculate_score(certified_asset, db_session)
    # Even if composite score is low or candidate_retire, certified status vetoes retirement
    action, conf, exp, risks, approval = lifecycle_rules.evaluate_asset(certified_asset, breakdown, evidence)

    assert action != LifecycleAction.RETIRE_CANDIDATE


def test_veto_low_usage_alone_cannot_justify_retirement_if_usage_active(db_session):
    # Power BI Asset with moderate usage (avg views >= 50) marked as candidate_retire
    asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.platform == "Power BI", AnalyticsAssets.lifecycle_status == "candidate_retire")
        .first()
    )
    assert asset is not None

    breakdown, evidence = scoring_engine.calculate_score(asset, db_session)
    # Set active usage and clear other veto triggers to isolate the usage veto
    evidence["usage"]["avg_views"] = 65.0
    evidence["lineage"]["downstream_dependent_count"] = 0
    evidence["reach"]["has_critical_kpi"] = False

    action, conf, exp, risks, approval = lifecycle_rules.evaluate_asset(asset, breakdown, evidence)

    # Must be routed to CONSOLIDATE rather than immediate retirement
    assert action == LifecycleAction.CONSOLIDATE
    assert "Retirement VETOED" in exp


def test_insufficient_evidence_forces_review(db_session):
    asset = db_session.query(AnalyticsAssets).first()
    breakdown, evidence = scoring_engine.calculate_score(asset, db_session)
    # Simulate zero recorded usage telemetry
    evidence["usage"]["months_recorded"] = 0

    action, conf, exp, risks, approval = lifecycle_rules.evaluate_asset(asset, breakdown, evidence)

    assert action == LifecycleAction.REVIEW
    assert conf <= 0.50
    assert "Insufficient evidence" in exp


def test_tableau_platform_routed_to_migrate(db_session):
    tableau_asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.platform == "Tableau")
        .first()
    )
    assert tableau_asset is not None

    breakdown, evidence = scoring_engine.calculate_score(tableau_asset, db_session)
    action, conf, exp, risks, approval = lifecycle_rules.evaluate_asset(tableau_asset, breakdown, evidence)

    assert action == LifecycleAction.MIGRATE
