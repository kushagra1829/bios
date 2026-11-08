import json
import os
import pytest
from sqlalchemy.orm import Session

from backend.app.artifacts.schemas import ArtifactGenerationRequest
from backend.app.artifacts.service import ArtifactService
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.artifacts.validator import (
    check_desktop_executable_available,
    validate_artifact,
)
from backend.app.db.session import SessionLocal


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_powerbi_ladder_g0_through_g4(db: Session, tmp_path):
    """
    Validates Power BI Artifact Factory Ladder G0–G4:
      - Level G0: Generation (directory structure, files, provenance, safe names)
      - Level G1: Per-File Validation (valid JSON schemas, TMDL compatibility 1567, PBIR syntax)
      - Level G2: Cross-Reference Validation (visual queryRefs resolve to defined columns/measures, relationships)
      - Level G3: Serializer & Semantic Integrity (no invented measures or tables, round-trip fidelity)
      - Level G4: Live Desktop Acceptance (truthfully reports UNVERIFIED when PBIDesktop.exe is not installed)
    """
    ladder_export_dir = str(tmp_path / "powerbi_ladder_tests")
    os.makedirs(ladder_export_dir, exist_ok=True)

    spec = build_dashboard_spec(
        title="Quality Ladder Commercial Verification",
        business_purpose="Testing G0-G4 ladder validation on canonical Bayer dataset",
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
        kpi_ids=["KPI-001", "KPI-004", "KPI-027"],
    )

    gen_req = ArtifactGenerationRequest(
        spec=spec,
        actor_id="QA_ARCHITECT",
        force=True,
    )

    artifact = ArtifactService.generate_artifact(
        db,
        gen_req,
        base_export_dir=ladder_export_dir,
    )

    # -------------------------------------------------------------
    # LEVEL G0: Generation Verification
    # -------------------------------------------------------------
    assert os.path.exists(artifact.output_directory), "G0 FAIL: Output directory missing"
    assert os.path.exists(artifact.root_pbip_file), "G0 FAIL: Root .pbip missing"
    assert "Quality_Ladder_Commercial_Verification" in artifact.artifact_name
    prov = json.loads(artifact.provenance_json)
    assert "spec_hash" in prov, "G0 FAIL: Specification hash missing from provenance"
    assert prov["file_count"] >= 7, "G0 FAIL: Incomplete file manifest"

    # -------------------------------------------------------------
    # LEVEL G1: Per-File Schema Validation
    # -------------------------------------------------------------
    with open(artifact.root_pbip_file, "r", encoding="utf-8") as f:
        pbip_json = json.load(f)
    assert pbip_json.get("version") == "1.0", "G1 FAIL: Root .pbip schema version must be 1.0"

    report_dir = os.path.join(artifact.output_directory, "Quality_Ladder_Commercial_Verification.Report")
    pbir_file = os.path.join(report_dir, "definition.pbir")
    assert os.path.exists(pbir_file), "G1 FAIL: definition.pbir missing"
    with open(pbir_file, "r", encoding="utf-8") as f:
        pbir_json = json.load(f)
    assert "datasetReference" in pbir_json, "G1 FAIL: definition.pbir missing datasetReference"

    model_dir = os.path.join(artifact.output_directory, "Quality_Ladder_Commercial_Verification.SemanticModel")
    db_tmdl = os.path.join(model_dir, "definition", "database.tmdl")
    assert os.path.exists(db_tmdl), "G1 FAIL: database.tmdl missing"
    with open(db_tmdl, "r", encoding="utf-8") as f:
        assert "compatibilityLevel: 1567" in f.read(), "G1 FAIL: database.tmdl compatibilityLevel must be 1567"

    # -------------------------------------------------------------
    # LEVEL G2: Cross-Reference Validation
    # -------------------------------------------------------------
    report = validate_artifact(artifact.output_directory, artifact.root_pbip_file, artifact.artifact_id)
    checks = {c.check_name: c.status for c in report.checks}
    assert checks["report_reference_integrity"] == "PASS", "G2 FAIL: Visual queryRef cross-references failed"
    assert checks["relationship_integrity"] == "PASS", "G2 FAIL: Key relationship cross-references failed"

    # -------------------------------------------------------------
    # LEVEL G3: Serializer & Semantic Integrity Validation
    # -------------------------------------------------------------
    assert checks["tmdl_tables_syntax"] == "PASS", "G3 FAIL: TMDL tables syntax or measures invalid"
    assert checks["tmdl_database_compatibility"] == "PASS", "G3 FAIL: Compatibility level verification failed"

    # -------------------------------------------------------------
    # LEVEL G4: Actual Power BI Desktop Acceptance
    # -------------------------------------------------------------
    desktop_available, desktop_path = check_desktop_executable_available()
    if desktop_available:
        assert checks["desktop_smoke_verification"] == "PASS"
        assert report.overall_status == "VALID"
    else:
        # Must honestly report UNVERIFIED without manufacturing a false pass
        assert checks["desktop_smoke_verification"] == "UNVERIFIED"
        assert "UNVERIFIED" in report.desktop_verification
        assert report.overall_status == "VALID_WITH_UNVERIFIED_DESKTOP"

