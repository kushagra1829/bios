from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class Products(Base):
    __tablename__ = "products"

    product_id = Column(String(10), primary_key=True)
    product_name = Column(String(50), nullable=False, unique=True, index=True)
    therapeutic_area = Column(String(50), nullable=False, index=True)
    product_type = Column(String(50), nullable=False)
    portfolio_stage = Column(String(100), nullable=False)
    commercial_scope = Column(String(50), nullable=False)
    public_context_only = Column(Boolean, nullable=False, default=True)


class Markets(Base):
    __tablename__ = "markets"

    market_id = Column(String(10), primary_key=True)
    market_name = Column(String(50), nullable=False, unique=True, index=True)
    region = Column(String(50), nullable=False, index=True)
    currency = Column(String(10), nullable=False)
    market_maturity = Column(String(30), nullable=False)
    regulatory_complexity = Column(String(20), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)


class ProductMarketMonthly(Base):
    __tablename__ = "product_market_monthly"

    product_id = Column(String(10), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    market_id = Column(String(10), ForeignKey("markets.market_id", ondelete="RESTRICT"), nullable=False, index=True)
    month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    net_sales_m_eur_syn = Column(Float, nullable=False)
    forecast_m_eur_syn = Column(Float, nullable=False)
    units_shipped_syn = Column(Integer, nullable=False)
    # CRITICAL: exactly 110 rows in Product_Market_Monthly have missing forecast variance.
    # Preserve NULL. Never invent or impute values.
    forecast_variance_pct = Column(Float, nullable=True)
    market_access_coverage_pct_syn = Column(Float, nullable=False)
    otif_pct_syn = Column(Float, nullable=False)
    inventory_weeks_syn = Column(Float, nullable=False)
    value_type = Column(String(50), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("product_id", "market_id", "month"),
    )

    product = relationship("Products")
    market = relationship("Markets")


class LaunchMilestones(Base):
    __tablename__ = "launch_milestones"

    milestone_id = Column(String(20), primary_key=True)
    product_id = Column(String(10), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    market_id = Column(String(10), ForeignKey("markets.market_id", ondelete="RESTRICT"), nullable=False, index=True)
    milestone_type = Column(String(50), nullable=False)
    milestone_date = Column(DateTime, nullable=False)
    status = Column(String(30), nullable=False)  # 'completed', 'on_track', 'delayed'
    business_impact = Column(String(30), nullable=False)  # 'critical', 'high'
    synthetic_record = Column(Boolean, nullable=False, default=True)

    product = relationship("Products")
    market = relationship("Markets")


class MarketAccess(Base):
    __tablename__ = "market_access"

    product_id = Column(String(10), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    market_id = Column(String(10), ForeignKey("markets.market_id", ondelete="RESTRICT"), nullable=False, index=True)
    reimbursement_status = Column(String(50), nullable=False)  # 'full_coverage', 'restricted_coverage', etc.
    coverage_model = Column(String(50), nullable=False)
    coverage_pct_syn = Column(Float, nullable=False)
    trend_status = Column(String(30), nullable=False)
    analytics_priority = Column(String(20), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("product_id", "market_id"),
    )

    product = relationship("Products")
    market = relationship("Markets")


class SupplyOperations(Base):
    __tablename__ = "supply_operations"

    product_id = Column(String(10), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    market_id = Column(String(10), ForeignKey("markets.market_id", ondelete="RESTRICT"), nullable=False, index=True)
    supply_source = Column(String(50), nullable=False)
    primary_mode = Column(String(30), nullable=False)
    otif_pct_syn = Column(Float, nullable=False)
    inventory_weeks_syn = Column(Float, nullable=False)
    forecast_accuracy_pct_syn = Column(Float, nullable=False)
    risk_status = Column(String(20), nullable=False)
    synthetic_record = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        PrimaryKeyConstraint("product_id", "market_id"),
    )

    product = relationship("Products")
    market = relationship("Markets")

