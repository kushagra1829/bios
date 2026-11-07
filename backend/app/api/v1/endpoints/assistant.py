import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.db.session import get_db
from backend.app.agents.orchestrator import orchestrator
from backend.app.agents.schemas import (
    AssistantRequestCreate,
    AssistantRequestOut,
    AssistantRecommendationOut,
    AgentTraceOut,
    AssistantWorkflowResponse,
)
from backend.app.models.assistant import (
    AssistantRequests,
    AgentExecutionTraces,
    AssistantRecommendations,
)

router = APIRouter()


@router.post("/requests", response_model=AssistantWorkflowResponse, status_code=status.HTTP_201_CREATED)
def submit_assistant_request(
    payload: AssistantRequestCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a natural-language business analytics request.
    Orchestrates the multi-agent intelligence layer (Intent, Discovery, KPI Intelligence,
    Duplication, Governance, Decision) to return an evidence-backed recommendation.
    """
    try:
        response = orchestrator.process_request(payload.prompt, db)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent orchestration failed: {str(e)}",
        )


@router.get("/requests", response_model=List[AssistantRequestOut])
def list_assistant_requests(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (pending, completed, failed)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List historical assistant requests with pagination."""
    query = db.query(AssistantRequests)
    if status_filter:
        query = query.filter(AssistantRequests.status == status_filter.lower())

    requests = (
        query.order_by(desc(AssistantRequests.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return requests


@router.get("/requests/{request_id}", response_model=AssistantRequestOut)
def get_assistant_request(
    request_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve details of a specific assistant request."""
    req = db.query(AssistantRequests).filter(AssistantRequests.request_id == request_id).first()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assistant request '{request_id}' not found.",
        )
    return req


@router.get("/requests/{request_id}/recommendation", response_model=AssistantRecommendationOut)
def get_assistant_recommendation(
    request_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve the synthesized decision recommendation for an assistant request."""
    rec = (
        db.query(AssistantRecommendations)
        .filter(AssistantRecommendations.request_id == request_id)
        .first()
    )
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recommendation found for request '{request_id}'.",
        )
    return rec


@router.get("/requests/{request_id}/trace", response_model=List[AgentTraceOut])
def get_assistant_execution_trace(
    request_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve the full ordered multi-agent execution trace for an assistant request."""
    traces = (
        db.query(AgentExecutionTraces)
        .filter(AgentExecutionTraces.request_id == request_id)
        .order_by(AgentExecutionTraces.step_order.asc())
        .all()
    )
    if not traces:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No execution traces found for request '{request_id}'.",
        )
    return traces

