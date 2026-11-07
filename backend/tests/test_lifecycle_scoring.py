import pytest
from backend.app.db.session import SessionLocal
from backend.app.lifecycle.scoring import scoring_engine
from backend.app.models.core import AnalyticsAssets


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_scoring_engine_composite_formula_integrity(db_session):
    # Verify published weights sum to exactly 1.00
    total_weights = (
        scoring_engine.WEIGHT_USAGE
        + scoring_engine.WEIGHT_REACH
        + scoring_engine.WEIGHT_GOVERNANCE
        + scoring_engine.WEIGHT_LINEAGE
        + scoring_engine.WEIGHT_KPI
        + scoring_engine.WEIGHT_SEMANTIC
    )
    assert abs(total_weights - 1.00) < 1e-6

    # Score sample asset
    asset = db_session.query(AnalyticsAssets).first()
    assert asset is not None

    breakdown, evidence = scoring_engine.calculate_score(asset, db_session)

    # Verify every sub-score is bounded in [0.0, 100.0]
    assert 0.0 <= breakdown.usage_score <= 100.0
    assert 0.0 <= breakdown.audience_reach_score <= 100.0
    assert 0.0 <= breakdown.governance_trust_score <= 100.0
    assert 0.0 <= breakdown.lineage_dependency_score <= 100.0
    assert 0.0 <= breakdown.kpi_quality_score <= 100.0
    assert 0.0 <= breakdown.semantic_health_score <= 100.0
    assert 0.0 <= breakdown.composite_score <= 100.0

    # Verify calculated composite score matches formula
    expected_composite = round(
        (0.25 * breakdown.usage_score)
        + (0.20 * breakdown.audience_reach_score)
        + (0.20 * breakdown.governance_trust_score)
        + (0.15 * breakdown.lineage_dependency_score)
        + (0.10 * breakdown.kpi_quality_score)
        + (0.10 * breakdown.semantic_health_score),
        1,
    )
    assert abs(breakdown.composite_score - expected_composite) <= 0.1


def test_endorsement_and_ownership_impact_on_governance_score(db_session):
    # Certified asset with active owner should have high governance trust score
    certified_asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.endorsement == "certified", AnalyticsAssets.owner_id.is_not(None))
        .first()
    )
    if certified_asset:
        breakdown, _ = scoring_engine.calculate_score(certified_asset, db_session)
        assert breakdown.governance_trust_score >= 80.0

    # Unowned asset should have penalised governance trust score
    unowned_asset = (
        db_session.query(AnalyticsAssets)
        .filter(AnalyticsAssets.owner_id.is_(None))
        .first()
    )
    if unowned_asset:
        breakdown, _ = scoring_engine.calculate_score(unowned_asset, db_session)
        # owner component is 0, so governance trust cannot exceed 50
        assert breakdown.governance_trust_score <= 50.0


def test_downstream_dependencies_boost_lineage_score(db_session):
    asset = db_session.query(AnalyticsAssets).first()

    # Score with 0 dependents
    breakdown_zero, _ = scoring_engine.calculate_score(asset, db_session, downstream_dependents_count=0)

    # Score with 3 dependents
    breakdown_dep, _ = scoring_engine.calculate_score(asset, db_session, downstream_dependents_count=3)

    assert breakdown_dep.lineage_dependency_score > breakdown_zero.lineage_dependency_score
    assert breakdown_dep.lineage_dependency_score == 100.0

