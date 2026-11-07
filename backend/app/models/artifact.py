from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class DashboardSpecifications(Base):
    __tablename__ = "dashboard_specifications"

    spec_id = Column(String(50), primary_key=True)
    title = Column(String(255), nullable=False)
    business_purpose = Column(Text, nullable=False)
    request_id = Column(String(50), nullable=True, index=True)
    approval_id = Column(String(50), nullable=True, index=True)
    product_scope = Column(String(50), nullable=False, index=True)
    market_scope = Column(String(50), nullable=False, index=True)
    semantic_model_id = Column(String(50), nullable=True, index=True)
    spec_json = Column(Text, nullable=False)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    artifacts = relationship("GeneratedArtifacts", back_populates="specification", cascade="all, delete-orphan")


class GeneratedArtifacts(Base):
    __tablename__ = "generated_artifacts"

    artifact_id = Column(String(50), primary_key=True)
    spec_id = Column(String(50), ForeignKey("dashboard_specifications.spec_id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_name = Column(String(255), nullable=False)
    format = Column(String(20), nullable=False, default="PBIP")  # PBIP
    output_directory = Column(Text, nullable=False)
    root_pbip_file = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="generated", index=True)  # generated, validated, validation_failed, published
    provenance_json = Column(Text, nullable=False)
    validation_status = Column(String(30), nullable=False, default="pending", index=True)  # pending, valid, invalid
    validation_report_json = Column(Text, nullable=True)
    generated_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    validated_at = Column(DateTime, nullable=True)

    specification = relationship("DashboardSpecifications", back_populates="artifacts")

