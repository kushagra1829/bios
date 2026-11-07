import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from backend.app.db.session import Base
from backend.app.ingestion.loader import WorkbookIngestionService, DEFAULT_WORKBOOK_PATH
from backend.app.models.core import AnalyticsAssets, Owners, Workspaces, SemanticModels
from backend.app.models.domain import ProductMarketMonthly, Products, Markets
from backend.app.models.audit import SourceImportRuns, StagingWorkbookRaw


@pytest.fixture(scope="module")
def isolated_db_engine():
    # Use in-memory SQLite with a fresh metadata create
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="module")
def isolated_session_factory(isolated_db_engine):
    return sessionmaker(bind=isolated_db_engine)


def test_dry_run_does_not_modify_database(isolated_session_factory):
    service = WorkbookIngestionService(session_factory=isolated_session_factory)
    report = service.ingest_workbook(dry_run=True)

    assert report.status == "dry_run"
    assert report.total_records == 8148
    assert report.total_inserted == 8148  # simulated count
    assert len(report.validation_errors) == 0

    # Ensure no rows were committed to database
    with isolated_session_factory() as session:
        count = session.execute(select(func.count(AnalyticsAssets.asset_id))).scalar()
        assert count == 0
        runs_count = session.execute(select(func.count(SourceImportRuns.import_id))).scalar()
        assert runs_count == 0


def test_real_ingestion_loads_all_records(isolated_session_factory):
    service = WorkbookIngestionService(session_factory=isolated_session_factory)
    report = service.ingest_workbook(dry_run=False)

    assert report.status == "success"
    assert report.total_records == 8148
    assert report.total_inserted == 8148
    assert report.total_updated == 0
    assert report.total_unchanged == 0
    assert len(report.validation_errors) == 0

    # Check key entity counts
    with isolated_session_factory() as session:
        assert session.execute(select(func.count(Workspaces.workspace_id))).scalar() == 16
        assert session.execute(select(func.count(Owners.owner_id))).scalar() == 60
        assert session.execute(select(func.count(SemanticModels.model_id))).scalar() == 75
        assert session.execute(select(func.count(AnalyticsAssets.asset_id))).scalar() == 360
        assert session.execute(select(func.count(Products.product_id))).scalar() == 7
        assert session.execute(select(func.count(Markets.market_id))).scalar() == 14
        assert session.execute(select(func.count(ProductMarketMonthly.product_id))).scalar() == 980

        # Verify intentional missing values are preserved
        unowned_count = session.execute(
            select(func.count(AnalyticsAssets.asset_id)).where(AnalyticsAssets.owner_id == None)
        ).scalar()
        assert unowned_count == 21, "Must preserve exactly 21 unowned assets"

        null_var_count = session.execute(
            select(func.count(ProductMarketMonthly.product_id)).where(ProductMarketMonthly.forecast_variance_pct == None)
        ).scalar()
        assert null_var_count == 110, "Must preserve exactly 110 null forecast variance values"

        # Verify raw staging records: 8,100 relational + 48 documentation = 8,148
        staging_count = session.execute(select(func.count(StagingWorkbookRaw.id))).scalar()
        assert staging_count == 8148


def test_repeated_ingestion_is_idempotent(isolated_session_factory):
    """Re-importing the same workbook must not duplicate records; all 8148 rows must be reported unchanged."""
    service = WorkbookIngestionService(session_factory=isolated_session_factory)
    report = service.ingest_workbook(dry_run=False)

    assert report.status == "success"
    assert report.total_records == 8148
    assert report.total_inserted == 0, "Idempotent re-run must insert 0 records"
    assert report.total_updated == 0, "Idempotent re-run must update 0 records"
    assert report.total_unchanged == 8148, "All 8148 records must be recognized as unchanged"
    assert len(report.validation_errors) == 0

    # Database totals must remain identical
    with isolated_session_factory() as session:
        assert session.execute(select(func.count(AnalyticsAssets.asset_id))).scalar() == 360
        assert session.execute(select(func.count(ProductMarketMonthly.product_id))).scalar() == 980


def test_missing_file_raises_error():
    service = WorkbookIngestionService()
    with pytest.raises(FileNotFoundError):
        service.ingest_workbook(workbook_path=DEFAULT_WORKBOOK_PATH.parent / "non_existent_file.xlsx")

