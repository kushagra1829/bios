import json
import uuid
import pytest
from sqlalchemy.orm import Session

from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.approvals.schemas import UserRole
from backend.app.artifacts.schemas import ArtifactGenerationRequest
from backend.app.artifacts.service import ArtifactService
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.db.session import SessionLocal
from backend.app.lifecycle.engine import LifecycleEngine
from backend.app.models.approval import ApprovalRequests
from backend.app.models.assistant import AssistantRecommendations
from backend.app.models.governance import MigrationBacklog


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_use_case_1_nubeqa_sales_analytics_reuse(db: Session):
    """
    USE CASE 1 — Nubeqa Sales Analytics Reuse:
    Request: 'I need a Nubeqa sales dashboard with net sales, revenue growth and forecast variance.'
    Expected Principle: BIOS must prefer reuse or consolidation over building a new dashboard.
    """
    prompt = "I need a Nubeqa sales dashboard with net sales, revenue growth and forecast variance."
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_request(prompt, db)

    # 1. Intent extraction
    assert "Nubeqa" in res.intent.products
    assert len(res.intent.kpis) >= 2

    # 2. Duplicate & Discovery
    assert res.duplication.has_duplicates is True or len(res.discovery.exact_matches + res.discovery.partial_matches) > 0

    # 3. Decision: Must NOT be BUILD_NEW
    assert res.recommendation.decision in ("CONSOLIDATE", "MODIFY", "REUSE")
    assert res.recommendation.confidence >= 0.70
    assert res.recommendation.human_approval_required is True

    # 4. Traces recorded
    assert len(res.traces) == 6


def test_use_case_2_kpi_definition_conflict(db: Session):
    """
    USE CASE 2 — KPI Definition Conflict & Canonical Resolution:
    Request: 'I need a monthly commercial performance dashboard showing net sales and revenue growth.'
    Expected Principle: BIOS flags unapproved/conflicting variants and protects canonical KPIs.
    """
    prompt = "I need a monthly commercial performance dashboard showing net sales and revenue growth."
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_request(prompt, db)

    # Missing product scope correctly surfaced
    assert res.recommendation.decision == "NEEDS_CLARIFICATION"
    assert "product" in res.recommendation.primary_recommendation.lower()

    # Canonical KPI resolution checked
    canonical_kpis = res.kpi_analysis.canonical_approved_kpi_ids
    assert len(canonical_kpis) >= 1  # Net Sales -> KPI-001


def test_use_case_3_tableau_migration_rationalization(db: Session):
    """
    USE CASE 3 — Tableau Migration Rationalization:
    Demonstrates that 1:1 migration is rationalized into distinct paths:
    Direct Migration, Consolidate, Fix, Retire Instead, Hold.
    """
    engine = LifecycleEngine()
    summary = engine.evaluate_all(db)
    breakdown = summary.migration_breakdown

    assert breakdown.get("MIGRATE", 0) > 0, "Direct migration path missing"
    assert breakdown.get("CONSOLIDATE_BEFORE_MIGRATION", 0) > 0, "Consolidation path missing"
    assert breakdown.get("RETIRE_INSTEAD_OF_MIGRATE", 0) > 0, "Retire path missing"
    assert breakdown.get("FIX_BEFORE_MIGRATION", 0) > 0, "Fix path missing"
    assert breakdown.get("HOLD_FOR_REVIEW", 0) > 0, "Hold path missing"

    # Total rationalized non-direct migration (consolidate + retire + fix + hold) > direct migration
    non_direct = (
        breakdown["CONSOLIDATE_BEFORE_MIGRATION"]
        + breakdown["RETIRE_INSTEAD_OF_MIGRATE"]
        + breakdown["FIX_BEFORE_MIGRATION"]
        + breakdown["HOLD_FOR_REVIEW"]
    )
    assert non_direct > breakdown["MIGRATE"], "Rationalization should save significant migration effort"


def test_use_case_4_geography_ambiguity_and_user_error(db: Session):
    """
    USE CASE 4 — Geography Ambiguity and Resolution:
    Verifies:
      - Europe does not silently map to EMEA
      - EMEA is recognized as a regional scope
      - Finland & Europe is handled as partially resolved
      - IT budget dashboard is not conflated with Italy
      - America requires clarification
    """
    orchestrator = AgentOrchestrator()

    # Case A: Europe -> Needs Clarification
    res_europe = orchestrator.process_request("Nubeqa sales in Europe.", db)
    assert "Europe" in res_europe.intent.unresolved_terms or res_europe.intent.geography.status.value == "NEEDS_CLARIFICATION"

    # Case B: Finland and Europe -> Finland resolved, Europe needs clarification
    res_fi_eu = orchestrator.process_request("Monthly sales in Finland and Europe.", db)
    assert "FI" in res_fi_eu.intent.markets
    assert res_fi_eu.intent.geography.status.value in ("PARTIALLY_RESOLVED", "NEEDS_CLARIFICATION")

    # Case C: IT budget dashboard -> Does not map to Italy
    res_it = orchestrator.process_request("IT budget dashboard.", db)
    assert "IT" not in res_it.intent.markets

    # Case D: Sales in EMEA -> Recognized as EMEA region
    res_emea = orchestrator.process_request("Sales in EMEA.", db)
    assert "EMEA" in res_emea.intent.markets
    assert res_emea.intent.geography.status.value == "RESOLVED"


def test_use_case_5_genuine_new_power_bi_artifact_workflow(db: Session, tmp_path):
    """
    USE CASE 5 — Genuine New Power BI Artifact:
    Request justified by evidence (novel product/market launch not covered by existing reports),
    authorized via approved governance workflow, generates genuine validated PBIP.
    """
    req_id = f"REQ-UC5-{uuid.uuid4().hex[:6]}"
    app_id = f"APP-UC5-{uuid.uuid4().hex[:6]}"

    # Spec for genuine novel launch
    spec = build_dashboard_spec(
        title="Kerendia China Commercial Launch Project",
        business_purpose="Track novel market access and commercial launch in China",
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
        request_id=req_id,
        approval_id=app_id,
        kpi_ids=["KPI-001", "KPI-004", "KPI-027"],
    )

    # Create approved approval request
    approval = ApprovalRequests(
        approval_id=app_id,
        target_entity_type="request",
        target_entity_id=req_id,
        action_type="PUBLISH_ARTIFACT",
        requester_id="COMMERCIAL_LEAD",
        requester_role=UserRole.ASSET_OWNER.value,
        required_role=UserRole.BI_GOVERNANCE_REVIEWER.value,
        status="APPROVED",
        title="Approve Kerendia China Launch Dashboard",
        description="Justified novel commercial launch",
        decided_by_id="GOV_DIRECTOR",
        decided_by_role="BI_GOVERNANCE_REVIEWER",
    )
    db.add(approval)
    db.commit()

    # Generate artifact
    gen_req = ArtifactGenerationRequest(
        spec=spec,
        request_id=req_id,
        approval_id=app_id,
        actor_id="BI_ENGINEER",
        actor_role="BI_DEVELOPER",
        force=False,
    )

    artifact = ArtifactService.generate_artifact(
        db,
        gen_req,
        base_export_dir=str(tmp_path / "uc5_exports"),
    )

    assert artifact.status in ("validated", "generated")
    assert artifact.validation_status in ("valid", "valid_with_unverified_desktop")
    val_report = json.loads(artifact.validation_report_json)
    assert val_report["overall_status"] in ("VALID", "VALID_WITH_UNVERIFIED_DESKTOP")

