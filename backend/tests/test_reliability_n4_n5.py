import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import Session

from backend.app.approvals.roles import role_manager
from backend.app.approvals.schemas import (
    ApprovalActionType,
    ApprovalCreate,
    ApprovalDecisionPayload,
    ApprovalStatus,
    UserRole,
)
from backend.app.approvals.service import ApprovalService
from backend.app.artifacts.schemas import ArtifactGenerationRequest, DashboardSpec
from backend.app.artifacts.service import ApprovalRequiredError, ArtifactService
from backend.app.db.session import SessionLocal
from backend.app.models.approval import ApprovalRequests, AuditEvents
from backend.app.models.core import AnalyticsAssets, Owners


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# =========================================================================
# PRIORITY 1: FIX N4 — LIVE INACTIVE-OWNER VERIFICATION TESTS
# =========================================================================

def test_n4_active_owner_can_approve_valid_request(db: Session):
    """Active owner in database can approve valid request within their scope."""
    # Find an asset with an active owner
    asset_with_active_owner = (
        db.query(AnalyticsAssets)
        .join(Owners, AnalyticsAssets.owner_id == Owners.owner_id)
        .filter(Owners.status == "active")
        .first()
    )
    assert asset_with_active_owner is not None
    active_owner_id = asset_with_active_owner.owner_id

    app_id = f"APP-N4-ACTIVE-{uuid.uuid4().hex[:6]}"
    req = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="asset",
        target_entity_id=asset_with_active_owner.asset_id,
        action_type=ApprovalActionType.CONSOLIDATE.value,
        requester_id="REQ-USER-1",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.ASSET_OWNER.value,
        status=ApprovalStatus.PENDING.value,
        title="Valid Active Owner Approval",
        description="Testing active owner authorization",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(req)
    db.commit()

    decision = ApprovalDecisionPayload(
        actor_id=active_owner_id,
        actor_role=UserRole.ASSET_OWNER,
        decision=ApprovalStatus.APPROVED,
        reason="Consolidation approved by active authoritative owner.",
    )
    res = ApprovalService.approve_request(app_id, decision, db)
    assert res.status == ApprovalStatus.APPROVED.value
    assert res.decided_by_id == active_owner_id


def test_n4_inactive_owner_cannot_approve(db: Session):
    """Inactive owner in authoritative database is strictly blocked."""
    inactive_owner = db.query(Owners).filter(Owners.status != "active").first()
    assert inactive_owner is not None

    app_id = f"APP-N4-INACTIVE-{uuid.uuid4().hex[:6]}"
    req = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="asset",
        target_entity_id="AST-0001",
        action_type=ApprovalActionType.CONSOLIDATE.value,
        requester_id="REQ-USER-2",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.ASSET_OWNER.value,
        status=ApprovalStatus.PENDING.value,
        title="Unauthorized Inactive Owner Attempt",
        description="Testing rejection of inactive owner",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(req)
    db.commit()

    decision = ApprovalDecisionPayload(
        actor_id=inactive_owner.owner_id,
        actor_role=UserRole.ASSET_OWNER,
        decision=ApprovalStatus.APPROVED,
        reason="Attempting approval while inactive",
    )
    with pytest.raises(PermissionError) as exc:
        ApprovalService.approve_request(app_id, decision, db)
    assert "Inactive owner authorization prohibited" in str(exc.value)

    # Verify audit event was logged
    audit = db.query(AuditEvents).filter(
        AuditEvents.target_entity_id == "AST-0001",
        AuditEvents.event_type.in_(["UNAUTHORIZED_INACTIVE_OWNER", "UNAUTHORIZED_APPROVAL_ATTEMPT"]),
    ).order_by(AuditEvents.created_at.desc()).first()
    assert audit is not None


def test_n4_owner_becomes_inactive_after_creation_before_approval(db: Session):
    """An owner active when request was created but deactivated before approval is caught."""
    temp_owner_id = f"OWN-TEMP-{uuid.uuid4().hex[:6]}"
    temp_owner = Owners(
        owner_id=temp_owner_id,
        owner_name="Temporary Owner",
        role="Product Owner",
        scope="Commercial",
        status="active",
        email=f"{temp_owner_id}@bayer.test",
        synthetic_record=True,
    )
    db.add(temp_owner)
    db.commit()

    try:
        app_id = f"APP-N4-STALE-{uuid.uuid4().hex[:6]}"
        req = ApprovalRequests(
            approval_id=app_id,
            target_entity_type="asset",
            target_entity_id="AST-0001",
            action_type=ApprovalActionType.CONSOLIDATE.value,
            requester_id="REQ-USER-3",
            requester_role=UserRole.REQUESTER.value,
            required_role=UserRole.ASSET_OWNER.value,
            status=ApprovalStatus.PENDING.value,
            title="Stale Request Deactivation Test",
            description="Testing deactivation between creation and approval",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(req)
        db.commit()

        # Now simulate HR/IAM deactivation right before review execution
        temp_owner.status = "inactive"
        db.commit()

        decision = ApprovalDecisionPayload(
            actor_id=temp_owner_id,
            actor_role=UserRole.ASSET_OWNER,
            decision=ApprovalStatus.APPROVED,
            reason="Approving with stale active assumption",
        )
        with pytest.raises(PermissionError) as exc:
            ApprovalService.approve_request(app_id, decision, db)
        assert "Inactive owner authorization prohibited" in str(exc.value)
    finally:
        db.query(Owners).filter(Owners.owner_id == temp_owner_id).delete()
        db.commit()


def test_n4_missing_or_forged_owner_identity_rejected(db: Session):
    """Missing or forged owner ID is rejected with missing owner error."""
    app_id = f"APP-N4-FORGED-{uuid.uuid4().hex[:6]}"
    req = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="asset",
        target_entity_id="AST-0001",
        action_type=ApprovalActionType.CONSOLIDATE.value,
        requester_id="REQ-USER-4",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.ASSET_OWNER.value,
        status=ApprovalStatus.PENDING.value,
        title="Forged Owner Attempt",
        description="Testing forged owner ID rejection",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(req)
    db.commit()

    decision = ApprovalDecisionPayload(
        actor_id="GHOST_OWNER_NONEXISTENT",
        actor_role=UserRole.ASSET_OWNER,
        decision=ApprovalStatus.APPROVED,
        reason="Forged owner identity",
    )
    with pytest.raises(PermissionError) as exc:
        ApprovalService.approve_request(app_id, decision, db)
    assert "Missing or invalid owner record" in str(exc.value)


def test_n4_owner_scope_mismatch_rejected(db: Session):
    """Active owner of Asset A cannot approve changes for Asset B that they do not own."""
    # Find two assets with distinct active owners
    assets = (
        db.query(AnalyticsAssets)
        .join(Owners, AnalyticsAssets.owner_id == Owners.owner_id)
        .filter(Owners.status == "active")
        .limit(2)
        .all()
    )
    assert len(assets) >= 2
    asset_a = assets[0]
    # Find an active owner who is NOT asset_a's owner
    other_owner = (
        db.query(Owners)
        .filter(Owners.status == "active", Owners.owner_id != asset_a.owner_id)
        .first()
    )
    assert other_owner is not None

    app_id = f"APP-N4-SCOPE-{uuid.uuid4().hex[:6]}"
    req = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="asset",
        target_entity_id=asset_a.asset_id,
        action_type=ApprovalActionType.CONSOLIDATE.value,
        requester_id="REQ-USER-5",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.ASSET_OWNER.value,
        status=ApprovalStatus.PENDING.value,
        title="Out-of-Scope Owner Attempt",
        description="Testing owner scope mismatch",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(req)
    db.commit()

    # other_owner attempts to approve asset_a
    decision = ApprovalDecisionPayload(
        actor_id=other_owner.owner_id,
        actor_role=UserRole.ASSET_OWNER,
        decision=ApprovalStatus.APPROVED,
        reason="Attempting to approve another owner's asset",
    )
    with pytest.raises(PermissionError) as exc:
        ApprovalService.approve_request(app_id, decision, db)
    assert "Owner scope mismatch" in str(exc.value)


# =========================================================================
# PRIORITY 2: FIX N5 — SYNCHRONOUS EXPIRED-WAIVER ENFORCEMENT TESTS
# =========================================================================

def test_n5_valid_active_waiver_accepted(db: Session):
    """Valid unexpired approved waiver passes synchronous verification."""
    waiver_id = f"WAV-VALID-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    waiver = ApprovalRequests(
        approval_id=waiver_id,
        target_entity_type="asset",
        target_entity_id="AST-0010",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="LEAD-1",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,
        title="Valid Temporary Exception",
        description="Documented exception for lineage testing",
        created_at=now_utc - timedelta(days=1),
        updated_at=now_utc - timedelta(days=1),
        expires_at=now_utc + timedelta(days=14),  # Valid for 14 more days
    )
    db.add(waiver)
    db.commit()

    verified = ApprovalService.verify_waiver_synchronous(
        db=db,
        waiver_id=waiver_id,
        target_entity_id="AST-0010",
    )
    assert verified.approval_id == waiver_id
    assert verified.status == ApprovalStatus.APPROVED.value


def test_n5_expired_waiver_rejected_synchronously(db: Session):
    """Expired waiver is synchronously rejected even if DB status is still APPROVED."""
    waiver_id = f"WAV-EXPIRED-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    waiver = ApprovalRequests(
        approval_id=waiver_id,
        target_entity_type="asset",
        target_entity_id="AST-0010",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="LEAD-1",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,  # Stale approved!
        title="Stale Approved Expired Waiver",
        description="Testing rejection of stale approved waiver past expiration",
        created_at=now_utc - timedelta(days=35),
        updated_at=now_utc - timedelta(days=35),
        expires_at=now_utc - timedelta(hours=2),  # Expired 2 hours ago
    )
    db.add(waiver)
    db.commit()

    with pytest.raises(PermissionError) as exc:
        ApprovalService.verify_waiver_synchronous(
            db=db,
            waiver_id=waiver_id,
            target_entity_id="AST-0010",
        )
    assert "Expired waiver veto" in str(exc.value)

    # Verify status in database was synchronously transitioned to EXPIRED
    db.refresh(waiver)
    assert waiver.status == ApprovalStatus.EXPIRED.value

    # Verify audit event was logged
    audit = db.query(AuditEvents).filter(
        AuditEvents.target_entity_id == "AST-0010",
        AuditEvents.event_type == "EXPIRED_WAIVER_USE_REJECTED",
    ).order_by(AuditEvents.created_at.desc()).first()
    assert audit is not None


def test_n5_approval_request_expired_before_decision_rejected(db: Session):
    """An approval request whose expiry date passed cannot be approved."""
    app_id = f"APP-EXPIRED-PENDING-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    req = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="asset",
        target_entity_id="AST-0020",
        action_type=ApprovalActionType.RETIRE.value,
        requester_id="DEV-1",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.PENDING.value,
        title="Pending Request Past Expiry",
        description="Testing expiry check during approve_request",
        created_at=now_utc - timedelta(days=40),
        updated_at=now_utc - timedelta(days=40),
        expires_at=now_utc - timedelta(days=5),  # Expired 5 days ago
    )
    db.add(req)
    db.commit()

    decision = ApprovalDecisionPayload(
        actor_id="GOV-REVIEWER-1",
        actor_role=UserRole.BI_GOVERNANCE_REVIEWER,
        decision=ApprovalStatus.APPROVED,
        reason="Late approval attempt",
    )
    with pytest.raises(PermissionError) as exc:
        ApprovalService.approve_request(app_id, decision, db)
    assert "Expired Request Veto" in str(exc.value)

    # Verify request status in DB was set to EXPIRED
    db.refresh(req)
    assert req.status == ApprovalStatus.EXPIRED.value


def test_n5_revoked_or_rejected_waiver_rejected(db: Session):
    """Waiver with status REJECTED or REVOKED is rejected synchronously."""
    waiver_id = f"WAV-REVOKED-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    waiver = ApprovalRequests(
        approval_id=waiver_id,
        target_entity_type="asset",
        target_entity_id="AST-0030",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="LEAD-2",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.REJECTED.value,
        title="Rejected Waiver",
        description="Testing rejected waiver",
        created_at=now_utc - timedelta(days=1),
        expires_at=now_utc + timedelta(days=10),
    )
    db.add(waiver)
    db.commit()

    with pytest.raises(PermissionError) as exc:
        ApprovalService.verify_waiver_synchronous(db=db, waiver_id=waiver_id)
    assert "Invalid waiver state" in str(exc.value)


def test_n5_out_of_scope_waiver_rejected(db: Session):
    """Waiver scoped to Asset A cannot be used to authorize an exception for Asset B."""
    waiver_id = f"WAV-SCOPE-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    waiver = ApprovalRequests(
        approval_id=waiver_id,
        target_entity_type="asset",
        target_entity_id="AST-0050",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="LEAD-3",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,
        title="Asset 50 Exception",
        description="Scoped exception for AST-0050",
        created_at=now_utc - timedelta(days=1),
        expires_at=now_utc + timedelta(days=10),
    )
    db.add(waiver)
    db.commit()

    with pytest.raises(PermissionError) as exc:
        ApprovalService.verify_waiver_synchronous(
            db=db,
            waiver_id=waiver_id,
            target_entity_id="AST-0099",  # Different asset!
        )
    assert "Out-of-scope waiver" in str(exc.value)


def test_n5_rule_008_waiver_bypass_strictly_prohibited(db: Session):
    """RULE-008 (Explainability) cannot be bypassed via any waiver, active or not."""
    waiver_id = f"WAV-RULE008-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    waiver = ApprovalRequests(
        approval_id=waiver_id,
        target_entity_type="governance_rule",
        target_entity_id="RULE-008",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="LEAD-4",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,
        title="Illegitimate RULE-008 Waiver Attempt",
        description="Attempt to bypass RULE-008",
        created_at=now_utc - timedelta(days=1),
        expires_at=now_utc + timedelta(days=10),
    )
    db.add(waiver)
    db.commit()

    with pytest.raises(PermissionError) as exc:
        ApprovalService.verify_waiver_synchronous(
            db=db,
            waiver_id=waiver_id,
            target_entity_type="governance_rule",
            target_entity_id="RULE-008",
        )
    assert "RULE-008 Waiver Prohibited" in str(exc.value)


def test_n5_artifact_factory_synchronous_expiry_check(db: Session, tmp_path):
    """Artifact factory refuses to generate BUILD_NEW dashboard using an expired approval."""
    app_id = f"APP-ARTIFACT-EXP-{uuid.uuid4().hex[:6]}"
    now_utc = datetime.now(timezone.utc)
    expired_approval = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="request",
        target_entity_id="REQ-TEST-EXP",
        action_type=ApprovalActionType.PUBLISH_ARTIFACT.value,
        requester_id="DEV-5",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,  # Stale approved
        title="Expired Build Approval",
        description="Testing artifact factory expiration check",
        created_at=now_utc - timedelta(days=35),
        expires_at=now_utc - timedelta(hours=1),  # Expired 1 hour ago
    )
    db.add(expired_approval)
    db.commit()

    spec = DashboardSpec(
        spec_id="SPEC-TEST-EXP-01",
        title="Expired Approval Test Dashboard",
        business_purpose="Testing synchronous waiver expiry in factory",
        request_id="REQ-TEST-EXP",
        approval_id=app_id,
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
        kpi_ids=["KPI-001"],
    )

    gen_req = ArtifactGenerationRequest(
        spec=spec,
        actor_id="QA_TESTER",
        force=False,
    )

    with pytest.raises(ApprovalRequiredError) as exc:
        ArtifactService.generate_artifact(
            db=db,
            request=gen_req,
            base_export_dir=str(tmp_path / "exp_test"),
        )
    assert "Expired waiver veto" in str(exc.value) or "expired" in str(exc.value).lower()
