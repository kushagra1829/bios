import pytest
from backend.app.artifacts.schemas import DashboardSpec, VisualSpec
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.artifacts.template_manager import BAYER_TABLE_SCHEMAS, CANONICAL_KPI_MEASURES


def test_build_dashboard_spec_defaults():
    spec = build_dashboard_spec(
        title="Kerendia Commercial Performance",
        business_purpose="Track monthly net sales, volume, and forecast variance in China",
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
    )

    assert spec.spec_id.startswith("SPEC-")
    assert spec.title == "Kerendia Commercial Performance"
    assert spec.product_scope == "PRD-KERENDIA"
    assert spec.market_scope == "MKT-CN"
    assert "ProductMarketMonthly" in spec.tables
    assert "Products" in spec.tables
    assert "Markets" in spec.tables

    # Check default canonical measures
    measure_names = [m.name for m in spec.measures]
    assert "Total Net Sales (M EUR)" in measure_names
    assert "Forecast Variance %" in measure_names
    assert "Total Units Shipped" in measure_names

    # Check pages and visual types
    assert len(spec.pages) >= 1
    page1 = spec.pages[0]
    visual_types = [v.visual_type for v in page1.visuals]
    assert "card" in visual_types
    assert "line_chart" in visual_types
    assert "bar_chart" in visual_types
    assert "slicer" in visual_types


def test_build_dashboard_spec_custom_kpis():
    spec = build_dashboard_spec(
        title="Custom KPI Dashboard",
        business_purpose="Track only net sales and units shipped",
        product_scope="PRD-NUBEQA",
        market_scope="MKT-US",
        kpi_ids=["KPI-001", "KPI-027"],
    )

    measure_names = [m.name for m in spec.measures]
    assert "Total Net Sales (M EUR)" in measure_names
    assert "Total Units Shipped" in measure_names
    assert "Forecast Variance %" not in measure_names


def test_dashboard_spec_theme_tokens():
    spec = build_dashboard_spec(
        title="Theme Test",
        business_purpose="Testing theme tokens",
        product_scope="GLOBAL",
        market_scope="GLOBAL",
    )

    assert spec.theme_palette["primary"] == "#142438"  # Midnight
    assert spec.theme_palette["accent"] == "#3478F6"   # Intelligence Blue
    assert spec.theme_palette["success"] == "#16A085"  # Trust Green
    assert spec.theme_palette["background"] == "#F2F5F9"  # Cloud

