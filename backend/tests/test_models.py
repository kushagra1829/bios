import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.app.db.session import Base
from backend.app.models.core import Workspaces, Owners, SemanticModels, AnalyticsAssets, LineageEdges
from backend.app.models.domain import Products, Markets, ProductMarketMonthly
from backend.app.models.governance import KpiCatalog, AssetKpiMap, MigrationBacklog, GovernanceSignals


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


def test_workspaces_and_owners_creation(memory_db):
    ws = Workspaces(
        workspace_id="WS-001",
        workspace_name="Global Executive",
        scope="Global",
        environment="Production",
        platform="Power BI",
        governance_mode="managed",
        classification="internal",
    )
    owner = Owners(
        owner_id="OWN-001",
        owner_name="Test Owner",
        role="Commercial Lead",
        scope="Global",
        status="active",
        email="test@bayer-synthetic.com",
    )
    memory_db.add_all([ws, owner])
    memory_db.commit()

    saved_ws = memory_db.execute(select(Workspaces).where(Workspaces.workspace_id == "WS-001")).scalar_one()
    assert saved_ws.workspace_name == "Global Executive"
    saved_owner = memory_db.execute(select(Owners).where(Owners.owner_id == "OWN-001")).scalar_one()
    assert saved_owner.status == "active"


def test_analytics_assets_nullable_owner(memory_db):
    """Test that owner_id is explicitly nullable to preserve unowned production assets (RULE-003)."""
    ws = Workspaces(
        workspace_id="WS-TEST",
        workspace_name="Test WS",
        scope="Global",
        environment="Production",
        platform="Power BI",
        governance_mode="managed",
        classification="internal",
    )
    owner = Owners(
        owner_id="OWN-TEST",
        owner_name="Test Owner",
        role="Lead",
        scope="Global",
        status="active",
        email="owner@test.com",
    )
    model = SemanticModels(
        model_id="SM-TEST",
        model_name="Test Model",
        workspace_id="WS-TEST",
        product_scope="Nubeqa",
        region_scope="Global",
        model_type="Power BI semantic model",
        endorsement="certified",
        refresh_frequency="daily",
        refresh_status="healthy",
        owner_id="OWN-TEST",
        table_count=10,
        measure_count=20,
        ai_readiness="good",
        ai_issue_pattern="clear",
    )
    memory_db.add_all([ws, owner, model])
    memory_db.commit()

    # Asset with NULL owner_id
    asset_unowned = AnalyticsAssets(
        asset_id="AST-UNOWNED",
        asset_name="Unowned Report",
        asset_type="Report",
        platform="Power BI",
        workspace_id="WS-TEST",
        model_id="SM-TEST",
        product_scope="Nubeqa",
        market_scope="Global",
        owner_id=None,  # Nullable
        lifecycle_status="active",
        endorsement="none",
        estimated_audience=500,
        classification="internal",
        delivery_model="self_service",
    )
    memory_db.add(asset_unowned)
    memory_db.commit()

    retrieved = memory_db.execute(select(AnalyticsAssets).where(AnalyticsAssets.asset_id == "AST-UNOWNED")).scalar_one()
    assert retrieved.owner_id is None
    assert retrieved.asset_name == "Unowned Report"


def test_product_market_monthly_nullable_variance(memory_db):
    """Test that forecast_variance_pct preserves NULL for pre-forecast launch horizons."""
    product = Products(
        product_id="P-TEST",
        product_name="TestDrug",
        therapeutic_area="Oncology",
        product_type="Prescription medicine",
        portfolio_stage="Recent launch",
        commercial_scope="Global",
    )
    market = Markets(
        market_id="DE",
        market_name="Germany",
        region="EMEA",
        currency="EUR",
        market_maturity="mature",
        regulatory_complexity="high",
    )
    memory_db.add_all([product, market])
    memory_db.commit()

    pmm = ProductMarketMonthly(
        product_id="P-TEST",
        market_id="DE",
        month="2026-08",
        net_sales_m_eur_syn=12.5,
        forecast_m_eur_syn=10.0,
        units_shipped_syn=50000,
        forecast_variance_pct=None,  # Preserves NULL
        market_access_coverage_pct_syn=85.0,
        otif_pct_syn=98.5,
        inventory_weeks_syn=14.0,
        value_type="synthetic_commercial_measure",
    )
    memory_db.add(pmm)
    memory_db.commit()

    retrieved = memory_db.execute(
        select(ProductMarketMonthly).where(
            ProductMarketMonthly.product_id == "P-TEST",
            ProductMarketMonthly.market_id == "DE",
            ProductMarketMonthly.month == "2026-08",
        )
    ).scalar_one()
    assert retrieved.forecast_variance_pct is None
    assert retrieved.net_sales_m_eur_syn == 12.5

