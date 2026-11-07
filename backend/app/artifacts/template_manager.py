from typing import Any, Dict, List
from backend.app.artifacts.schemas import MeasureSpec, RelationshipSpec


# Canonical table schema definitions based strictly on official Bayer workbook
BAYER_TABLE_SCHEMAS: Dict[str, Dict[str, str]] = {
    "ProductMarketMonthly": {
        "product_id": "string",
        "market_id": "string",
        "month": "string",
        "net_sales_m_eur_syn": "double",
        "forecast_m_eur_syn": "double",
        "units_shipped_syn": "int64",
        "forecast_variance_pct": "double",
        "market_access_coverage_pct_syn": "double",
        "otif_pct_syn": "double",
        "inventory_weeks_syn": "double",
        "value_type": "string",
        "synthetic_record": "boolean",
    },
    "Products": {
        "product_id": "string",
        "product_name": "string",
        "therapeutic_area": "string",
        "product_type": "string",
        "portfolio_stage": "string",
        "commercial_scope": "string",
        "public_context_only": "boolean",
    },
    "Markets": {
        "market_id": "string",
        "market_name": "string",
        "region": "string",
        "currency": "string",
        "market_maturity": "string",
        "regulatory_complexity": "string",
        "synthetic_record": "boolean",
    },
    "MarketAccess": {
        "product_id": "string",
        "market_id": "string",
        "reimbursement_status": "string",
        "coverage_model": "string",
        "coverage_pct_syn": "double",
        "trend_status": "string",
        "analytics_priority": "string",
        "synthetic_record": "boolean",
    },
}

# Standard canonical measures mapped directly to Bayer KPI Catalog
CANONICAL_KPI_MEASURES: Dict[str, MeasureSpec] = {
    "KPI-001": MeasureSpec(
        name="Total Net Sales (M EUR)",
        dax_expression="SUM('ProductMarketMonthly'[net_sales_m_eur_syn])",
        table_name="ProductMarketMonthly",
        format_string="#,##0.00",
        description="Total Net Sales in Millions of EUR (Canonical KPI-001)",
        kpi_id="KPI-001",
    ),
    "KPI-004": MeasureSpec(
        name="Forecast Variance %",
        dax_expression="DIVIDE(SUM('ProductMarketMonthly'[net_sales_m_eur_syn]) - SUM('ProductMarketMonthly'[forecast_m_eur_syn]), SUM('ProductMarketMonthly'[forecast_m_eur_syn]), 0) * 100",
        table_name="ProductMarketMonthly",
        format_string="0.0%",
        description="Forecast variance percentage comparing actuals to forecast (Canonical KPI-004)",
        kpi_id="KPI-004",
    ),
    "KPI-027": MeasureSpec(
        name="Total Units Shipped",
        dax_expression="SUM('ProductMarketMonthly'[units_shipped_syn])",
        table_name="ProductMarketMonthly",
        format_string="#,##0",
        description="Total commercial units shipped across portfolio (Canonical KPI-027)",
        kpi_id="KPI-027",
    ),
    "TOTAL_FORECAST": MeasureSpec(
        name="Total Forecast (M EUR)",
        dax_expression="SUM('ProductMarketMonthly'[forecast_m_eur_syn])",
        table_name="ProductMarketMonthly",
        format_string="#,##0.00",
        description="Total monthly forecast in Millions of EUR",
        kpi_id=None,
    ),
    "AVG_OTIF": MeasureSpec(
        name="Average OTIF %",
        dax_expression="AVERAGE('ProductMarketMonthly'[otif_pct_syn])",
        table_name="ProductMarketMonthly",
        format_string="0.0%",
        description="Average on-time in-full delivery percentage",
        kpi_id=None,
    ),
}

# Standard star-schema relationships among canonical tables
CANONICAL_RELATIONSHIPS: List[RelationshipSpec] = [
    RelationshipSpec(
        name="rel_pmm_products",
        from_table="ProductMarketMonthly",
        from_column="product_id",
        to_table="Products",
        to_column="product_id",
        is_active=True,
        cross_filtering_behavior="oneDirection",
    ),
    RelationshipSpec(
        name="rel_pmm_markets",
        from_table="ProductMarketMonthly",
        from_column="market_id",
        to_table="Markets",
        to_column="market_id",
        is_active=True,
        cross_filtering_behavior="oneDirection",
    ),
    RelationshipSpec(
        name="rel_marketaccess_products",
        from_table="MarketAccess",
        from_column="product_id",
        to_table="Products",
        to_column="product_id",
        is_active=False,
        cross_filtering_behavior="oneDirection",
    ),
    RelationshipSpec(
        name="rel_marketaccess_markets",
        from_table="MarketAccess",
        from_column="market_id",
        to_table="Markets",
        to_column="market_id",
        is_active=False,
        cross_filtering_behavior="oneDirection",
    ),
]

# BIOS Design System palette tokens
BIOS_PALETTE = {
    "name": "BIOS Enterprise Theme",
    "dataColors": [
        "#142438",  # Midnight
        "#3478F6",  # Intelligence Blue
        "#16A085",  # Trust Green
        "#E5A12B",  # Warning Amber
        "#DC5252",  # Critical Red
        "#4A6572",  # Slate
        "#34495E",  # Dark Slate
        "#2C3E50",  # Deep Blue
    ],
    "background": "#F2F5F9",
    "foreground": "#142438",
    "tableAccent": "#3478F6",
}

