import pytest
from backend.app.db.session import SessionLocal
from backend.app.lifecycle.migration import migration_engine
from backend.app.lifecycle.schemas import MigrationAction


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_migration_engine_evaluates_all_94_tableau_assets(db_session):
    results = migration_engine.evaluate_tableau_assets(db_session)

    # Exactly 94 legacy Tableau assets in dataset
    assert len(results) == 94

    actions = {r["recommended_action"] for r in results}
    # Verify presence of core rationalisation classifications
    assert MigrationAction.MIGRATE.value in actions
    assert MigrationAction.CONSOLIDATE_BEFORE_MIGRATION.value in actions
    assert MigrationAction.RETIRE_INSTEAD_OF_MIGRATE.value in actions
    assert MigrationAction.FIX_BEFORE_MIGRATION.value in actions
    assert MigrationAction.HOLD_FOR_REVIEW.value in actions


def test_migration_downstream_dependency_blocks_retirement(db_session):
    results = migration_engine.evaluate_tableau_assets(db_session)

    # Any asset that had a RETIRE backlog recommendation but has downstream dependents
    # MUST be placed on HOLD_FOR_REVIEW
    held_with_dependents = [
        r for r in results
        if r["recommended_action"] == MigrationAction.HOLD_FOR_REVIEW.value
        and r["downstream_dependency_count"] > 0
    ]
    assert len(held_with_dependents) > 0
    for r in held_with_dependents:
        assert len(r["blockers"]) > 0 or len(r["warnings"]) > 0


def test_migration_effort_reduction_opportunity(db_session):
    results = migration_engine.evaluate_tableau_assets(db_session)

    retire_count = sum(1 for r in results if r["recommended_action"] == MigrationAction.RETIRE_INSTEAD_OF_MIGRATE.value)
    consolidate_count = sum(1 for r in results if r["recommended_action"] == MigrationAction.CONSOLIDATE_BEFORE_MIGRATION.value)

    avoided_count = retire_count + consolidate_count
    # Substantial rationalization opportunity (avoiding 1:1 migration for ~40-50% of Tableau reports)
    assert avoided_count >= 35

