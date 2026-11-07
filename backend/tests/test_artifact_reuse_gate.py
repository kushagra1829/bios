import uuid
import pytest
from sqlalchemy.orm import Session

from backend.app.artifacts.schemas import ArtifactGenerationRequest
from backend.app.artifacts.service import (
    ApprovalRequiredError,
    ArtifactService,
    ReuseGateVetoError,
)
from backend.app.db.session import SessionLocal
from backend.app.models.approval import ApprovalRequests
from backend.app.models.assistant import AssistantRecommendations, AssistantRequests


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_reuse_gate_blocks_consolidate(db_session: Session):
    req_id = f"REQ-TEST-CONSOLIDATE-{uuid.uuid4().hex[:6]}"
    
    # Create request & recommendation CONSOLIDATE
    assistant_req = AssistantRequests(
        request_id=req_id,
        raw_prompt="Build new Nubeqa dashboard for US market",
        status="completed",
    )
    rec = AssistantRecommendations(
        recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
        request_id=req_id,
        decision="CONSOLIDATE",
        confidence=0.88,
        primary_recommendation="Consolidate requirements into existing asset AST-0065",
        rationale="Asset AST-0065 already covers Nubeqa US commercial tracking",
    )
    db_session.add(assistant_req)
    db_session.add(rec)
    db_session.commit()

    # Attempt to generate artifact
    gen_req = ArtifactGenerationRequest(
        request_id=req_id,
        actor_id="USER-TEST",
        actor_role="REQUESTER",
    )

    with pytest.raises(ReuseGateVetoError) as exc_info:
        ArtifactService.generate_artifact(db_session, gen_req)

    assert "REUSE_GATE_VETO" in str(exc_info.value)
    assert "CONSOLIDATE" in str(exc_info.value)


def test_reuse_gate_blocks_reuse(db_session: Session):
    req_id = f"REQ-TEST-REUSE-{uuid.uuid4().hex[:6]}"
    
    assistant_req = AssistantRequests(
        request_id=req_id,
        raw_prompt="Need sales report for Xarelto",
        status="completed",
    )
    rec = AssistantRecommendations(
        recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
        request_id=req_id,
        decision="REUSE",
        confidence=0.95,
        primary_recommendation="Reuse existing certified asset AST-0012",
        rationale="Existing certified asset meets 100% of requested metrics",
    )
    db_session.add(assistant_req)
    db_session.add(rec)
    db_session.commit()

    gen_req = ArtifactGenerationRequest(
        request_id=req_id,
        actor_id="USER-TEST",
        actor_role="REQUESTER",
    )

    with pytest.raises(ReuseGateVetoError) as exc_info:
        ArtifactService.generate_artifact(db_session, gen_req)

    assert "REUSE_GATE_VETO" in str(exc_info.value)
    assert "REUSE" in str(exc_info.value)


def test_build_new_requires_approval(db_session: Session):
    req_id = f"REQ-TEST-BUILDNEW-{uuid.uuid4().hex[:6]}"
    
    assistant_req = AssistantRequests(
        request_id=req_id,
        raw_prompt="New market launch dashboard for Kerendia in China",
        status="completed",
    )
    rec = AssistantRecommendations(
        recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
        request_id=req_id,
        decision="BUILD_NEW",
        confidence=0.92,
        primary_recommendation="Build new Power BI dashboard for Kerendia China launch",
        rationale="No existing dashboard covers Kerendia launch in China",
    )
    db_session.add(assistant_req)
    db_session.add(rec)
    db_session.commit()

    # Attempt without approval -> must fail
    gen_req = ArtifactGenerationRequest(
        request_id=req_id,
        actor_id="USER-TEST",
        actor_role="REQUESTER",
    )

    with pytest.raises(ApprovalRequiredError) as exc_info:
        ArtifactService.generate_artifact(db_session, gen_req)

    assert "APPROVAL_REQUIRED" in str(exc_info.value)


def test_build_new_with_approved_request_succeeds(db_session: Session, tmp_path):
    req_id = f"REQ-TEST-APPROVED-{uuid.uuid4().hex[:6]}"
    app_id = f"APP-TEST-{uuid.uuid4().hex[:6]}"

    assistant_req = AssistantRequests(
        request_id=req_id,
        raw_prompt="Kerendia commercial dashboard in China",
        status="completed",
    )
    rec = AssistantRecommendations(
        recommendation_id=f"REC-{uuid.uuid4().hex[:6]}",
        request_id=req_id,
        decision="BUILD_NEW",
        confidence=0.92,
        primary_recommendation="Build new Power BI dashboard for Kerendia China",
        rationale="Approved business case",
    )
    approval = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="request",
        target_entity_id=req_id,
        action_type="PUBLISH_ARTIFACT",
        requester_id="USER-LEAD",
        requester_role="ASSET_OWNER",
        required_role="BI_GOVERNANCE_REVIEWER",
        status="APPROVED",
        title="Approve Kerendia China Build",
        description="Approved after governance validation",
        decided_by_id="GOV-ADMIN",
        decided_by_role="BI_GOVERNANCE_REVIEWER",
    )
    db_session.add(assistant_req)
    db_session.add(rec)
    db_session.add(approval)
    db_session.commit()

    gen_req = ArtifactGenerationRequest(
        request_id=req_id,
        approval_id=app_id,
        actor_id="GOV-ADMIN",
        actor_role="BI_GOVERNANCE_REVIEWER",
    )

    artifact = ArtifactService.generate_artifact(
        db_session,
        gen_req,
        base_export_dir=str(tmp_path),
    )

    assert artifact is not None
    assert artifact.status in ("validated", "generated")
    assert artifact.validation_status in ("valid", "valid_with_unverified_desktop")

