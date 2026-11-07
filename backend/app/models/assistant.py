from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


class AssistantRequests(Base):
    __tablename__ = "assistant_requests"

    request_id = Column(String(50), primary_key=True)
    raw_prompt = Column(Text, nullable=False)
    parsed_intent_json = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)  # pending, processing, completed, failed
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    traces = relationship("AgentExecutionTraces", back_populates="request", cascade="all, delete-orphan", order_by="AgentExecutionTraces.step_order")
    recommendation = relationship("AssistantRecommendations", back_populates="request", uselist=False, cascade="all, delete-orphan")


class AgentExecutionTraces(Base):
    __tablename__ = "agent_execution_traces"

    trace_id = Column(String(50), primary_key=True)
    request_id = Column(String(50), ForeignKey("assistant_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name = Column(String(50), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="success")  # success, failed, retried
    duration_ms = Column(Float, nullable=False, default=0.0)
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_metadata_json = Column(Text, nullable=True)  # AgentExecutionMetadata: provider, model, mode, tokens
    executed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    request = relationship("AssistantRequests", back_populates="traces")

    __table_args__ = (
        Index("ix_trace_request_step", "request_id", "step_order"),
    )


class AssistantRecommendations(Base):
    __tablename__ = "assistant_recommendations"

    recommendation_id = Column(String(50), primary_key=True)
    request_id = Column(String(50), ForeignKey("assistant_requests.request_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    decision = Column(String(30), nullable=False, index=True)  # REUSE, CONSOLIDATE, MODIFY, MIGRATE, BUILD_NEW, NEEDS_CLARIFICATION
    confidence = Column(Float, nullable=False, default=0.0)
    primary_recommendation = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    alternatives_json = Column(Text, nullable=True)
    blockers_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    matched_assets_json = Column(Text, nullable=True)
    kpi_analysis_json = Column(Text, nullable=True)
    duplicate_analysis_json = Column(Text, nullable=True)
    approval_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    request = relationship("AssistantRequests", back_populates="recommendation")

