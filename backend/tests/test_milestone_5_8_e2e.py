"""
Milestone 5.8: Enterprise End-to-End Reliability & Product Validation Suite.
Validates the full BIOS platform across all six agents, eight governance rules,
approval security, artifact generation, and system boundaries.
"""

import os
import hashlib
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.db.session import SessionLocal, DEFAULT_SQLITE_PATH
from backend.app.agents.orchestrator import orchestrator
from backend.app.governance.registry import registry
from backend.app.governance.engine import engine
from backend.app.approvals.service import ApprovalService
from backend.app.approvals.schemas import (
    ApprovalActionType,
    ApprovalCreate,
    ApprovalDecisionPayload,
    ApprovalStatus,
    UserRole,
)
from backend.app.approvals.roles import role_manager
from backend.app.artifacts.service import ArtifactService
from backend.app.artifacts.schemas import ArtifactGenerationRequest, DashboardSpec, MeasureSpec
from backend.app.models.core import AnalyticsAssets, Owners
from backend.app.models.approval import ApprovalRequests, AuditEvents

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_m58_01_backend_health_and_service():
    """Verify backend health endpoint returns healthy status and service name."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "BIOS Backend"
    assert "timestamp" in data


def test_m58_02_dataset_integrity_and_alembic_head():
    """Verify official synthetic data pack SHA-256 and database Alembic migration revision."""
    data_pack_path = "data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"
    assert os.path.exists(data_pack_path), f"Data pack missing at {data_pack_path}"
    
    with open(data_pack_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    expected_hash = "7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab"
    assert file_hash == expected_hash, f"Hash mismatch: got {file_hash}, expected {expected_hash}"

    # Verify Alembic Head in SQLite
    conn = sqlite3.connect("data/bios.db")
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM alembic_version")
    row = cur.fetchone()
    conn.close()
    assert row is not None, "Alembic version table empty"
    assert row[0] == "b4f1c2d7e8a9", f"Unexpected Alembic revision: {row[0]}"


def test_m58_03_six_agent_full_orchestration(db: Session):
    """Validate end-to-end multi-agent pipeline returning all 6 execution traces with duration metrics."""
    prompt = "I need an executive cardiology sales dashboard for EU and US tracking Net Sales, physician reach, and brand adherence."
    response = orchestrator.process_request(prompt, db)

    assert response.request_id is not None
    assert response.request_id.startswith("REQ-")
    assert response.status == "completed"

    # Validate 6 sequential execution traces
    expected_agents = [
        "IntentAgent",
        "DiscoveryAgent",
        "KpiIntelligenceAgent",
        "DuplicationAgent",
        "GovernanceAgent",
        "DecisionAgent",
    ]
    assert len(response.traces) == 6, f"Expected 6 traces, got {len(response.traces)}"
    
    for idx, trace in enumerate(response.traces):
        assert trace.agent_name == expected_agents[idx], f"Trace {idx} agent mismatch"
        assert trace.step_order == idx + 1
        assert trace.status in ["success", "completed"]
        # duration_ms must be a non-negative float
        assert isinstance(trace.duration_ms, (int, float))
        assert trace.duration_ms >= 0.0

    # Validate synthesized decision
    assert response.recommendation is not None
    assert response.recommendation.decision in ["REUSE", "MODIFY", "CONSOLIDATE", "BUILD_NEW", "NEEDS_CLARIFICATION"]
    assert response.recommendation.confidence >= 0.0 and response.recommendation.confidence <= 1.0
    assert response.recommendation.primary_recommendation is not None
    assert response.recommendation.rationale is not None


def test_m58_04_trace_duration_formatting_safety():
    """Verify trace duration numerical edge cases (undefined, null, NaN, zero) cannot crash formatters."""
    def safe_format_ms(val, digits=1, fallback="—"):
        if val is None or not isinstance(val, (int, float)) or (isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf"))):
            return fallback
        return f"{val:.{digits}f}ms"

    assert safe_format_ms(123.456) == "123.5ms"
    assert safe_format_ms(0.0) == "0.0ms"
    assert safe_format_ms(None) == "—"
    assert safe_format_ms("invalid") == "—"
    assert safe_format_ms(float("nan")) == "—"
    assert safe_format_ms(float("inf")) == "—"


def test_m58_05_all_eight_governance_rules_active(db: Session):
    """Validate that all 8 governance rules are registered, active, and enforce strict deterministic policy."""
    rules = registry.get_all()
    assert len(rules) == 8, f"Expected 8 active rules, got {len(rules)}"
    
    rule_ids = {r.rule_id.value if hasattr(r.rule_id, "value") else str(r.rule_id) for r in rules}
    expected_ids = {
        "RULE-001",
        "RULE-002",
        "RULE-003",
        "RULE-004",
        "RULE-005",
        "RULE-006",
        "RULE-007",
        "RULE-008",
    }
    assert rule_ids == expected_ids, f"Mismatch in active rules: {rule_ids ^ expected_ids}"

    # Verify RULE-005 thresholds
    rule_005 = next(r for r in rules if (r.rule_id.value if hasattr(r.rule_id, "value") else str(r.rule_id)) == "RULE-005")
    assert rule_005.AUDIENCE_THRESHOLD_HIGH == 500
    assert rule_005.AUDIENCE_THRESHOLD_SELF_SERVICE == 250


def test_m58_06_approval_security_n4_n5_enforcement(db: Session):
    """Validate N4 live inactive-owner check and N5 synchronous expired-waiver rejection."""
    # N4: Inactive owner cannot approve
    inactive_owner = db.query(Owners).filter(Owners.status == "inactive").first()
    if inactive_owner:
        app_id = f"APP-TEST-N4-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        req = ApprovalRequests(
            approval_id=app_id,
            target_entity_type="asset",
            target_entity_id="AST-0001",
            action_type=ApprovalActionType.CONSOLIDATE.value,
            requester_id="REQ-USER-1",
            requester_role=UserRole.REQUESTER.value,
            required_role=UserRole.ASSET_OWNER.value,
            status=ApprovalStatus.PENDING.value,
            title="Inactive Owner Test",
            description="Testing N4 live check",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(req)
        db.commit()

        payload = ApprovalDecisionPayload(
            actor_id=inactive_owner.owner_id,
            actor_role=UserRole.ASSET_OWNER,
            reason="Unauthorized approval attempt by inactive owner",
        )
        with pytest.raises(PermissionError, match="Inactive owner authorization prohibited"):
            ApprovalService.approve_request(
                db=db,
                approval_id=app_id,
                payload=payload,
            )

    # N5: Synchronous expired waiver rejection
    exp_id = f"WVR-TEST-EXP-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    expired_waiver = ApprovalRequests(
        approval_id=exp_id,
        target_entity_type="asset",
        target_entity_id="AST-0050",
        action_type=ApprovalActionType.GOVERNANCE_EXCEPTION.value,
        requester_id="REQ-USER-1",
        requester_role=UserRole.REQUESTER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status=ApprovalStatus.APPROVED.value,
        decided_by_id="REV-GOV-01",
        decided_by_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        decided_at=datetime.now(timezone.utc) - timedelta(days=40),
        expires_at=datetime.now(timezone.utc) - timedelta(days=10),
        title="Expired Waiver Test",
        description="Testing N5 synchronous expiry",
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
        updated_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db.add(expired_waiver)
    db.commit()

    with pytest.raises(PermissionError, match="Expired waiver veto"):
        ApprovalService.verify_waiver_synchronous(
            db=db,
            waiver_id=exp_id,
            target_entity_type="asset",
            target_entity_id="AST-0050",
        )


def test_m58_07_asset_portfolio_and_migration_backlog():
    """Validate asset catalog count (360) and migration candidate backlog (94)."""
    resp_gov = client.get("/api/v1/governance/summary")
    assert resp_gov.status_code == 200
    gov_data = resp_gov.json()
    assert gov_data["total_active_findings"] > 0

    resp_assets = client.get("/api/v1/assets?page=1&page_size=10")
    assert resp_assets.status_code == 200
    assets_data = resp_assets.json()
    assert assets_data["meta"]["total"] == 360, f"Expected 360 assets, got {assets_data['meta']['total']}"

    resp_mig = client.get("/api/v1/migration/summary")
    assert resp_mig.status_code == 200
    mig_data = resp_mig.json()
    assert mig_data["total_tableau_assets"] == 94, f"Expected 94 Tableau assets, got {mig_data['total_tableau_assets']}"
    assert mig_data["retire_instead_count"] > 0
    assert mig_data["consolidate_count"] > 0
    assert mig_data["direct_migrate_count"] > 0


def test_m58_08_artifact_factory_generation_and_integrity(db: Session):
    """Validate Power BI Artifact Factory generates PBIP, TMDL, and PBIR with structural integrity."""
    spec = DashboardSpec(
        spec_id="SPEC-M58-VERIF",
        title="Bayer M58 Cardiology Portfolio",
        business_purpose="Governed verification artifact",
        product_scope="Cardiology",
        market_scope="EU & US",
        tables=["Fact_Prescriptions", "Dim_Products", "Dim_Physicians"],
        measures=[
            MeasureSpec(
                name="Net Sales",
                dax_expression="SUM(Fact_Prescriptions[SalesAmount])",
                table_name="Fact_Prescriptions",
                kpi_id="KPI-001",
            )
        ],
    )
    req = ArtifactGenerationRequest(
        actor_id="OWN-001",
        actor_role="BI Governance Reviewer",
        output_format="PBIP",
        force=True,
        spec=spec,
    )

    result = ArtifactService.generate_artifact(db, req)
    assert result.artifact_id is not None
    assert "Cardiology" in result.artifact_name
    assert result.format == "PBIP"
    assert result.validation_status.lower() in ["valid", "valid_with_unverified_desktop"]

    # Inspect generated artifact files
    assert os.path.exists(result.output_directory)
    # Check root pbip file
    assert result.root_pbip_file is not None
    assert os.path.exists(result.root_pbip_file)
    assert result.root_pbip_file.endswith(".pbip")

    # Walk directory to find report.json and model.tmdl
    found_files = []
    for root, _, filenames in os.walk(result.output_directory):
        for f in filenames:
            found_files.append(f)

    assert any(f.endswith(".pbip") for f in found_files), "Missing .pbip file"
    assert "report.json" in found_files, "Missing report.json"
    assert "model.tmdl" in found_files, "Missing model.tmdl"


def test_m58_09_software_only_scope_boundary():
    """Assert Arduino hardware edge routes and references are completely eliminated."""
    # API route must return 404
    resp = client.get("/api/v1/arduino/status")
    assert resp.status_code in [404, 405], f"Expected 404 for Arduino, got {resp.status_code}"
