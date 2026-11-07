import json
import os
import pytest
from sqlalchemy.orm import Session

from backend.app.artifacts.schemas import ArtifactGenerationRequest
from backend.app.artifacts.service import ArtifactService
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.artifacts.validator import validate_artifact
from backend.app.db.session import SessionLocal


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_validator_clean_artifact(db_session: Session, tmp_path):
    spec = build_dashboard_spec(
        title="Validator Clean Test",
        business_purpose="Testing validation on valid artifact",
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
    )

    gen_req = ArtifactGenerationRequest(
        spec=spec,
        actor_id="TESTER",
        force=True,
    )

    artifact = ArtifactService.generate_artifact(
        db_session,
        gen_req,
        base_export_dir=str(tmp_path),
    )

    report = validate_artifact(artifact.output_directory, artifact.root_pbip_file, artifact.artifact_id)

    # All structural and schema checks must PASS
    check_map = {c.check_name: c.status for c in report.checks}
    assert check_map["file_structure_pbip"] == "PASS"
    assert check_map["file_structure_semantic_model"] == "PASS"
    assert check_map["file_structure_report"] == "PASS"
    assert check_map["pbip_json_schema"] == "PASS"
    assert check_map["pbir_schema"] == "PASS"
    assert check_map["report_json_schema"] == "PASS"
    assert check_map["tmdl_database_compatibility"] == "PASS"
    assert check_map["tmdl_tables_syntax"] == "PASS"
    assert check_map["report_reference_integrity"] == "PASS"
    assert check_map["relationship_integrity"] == "PASS"

    # Power BI Desktop check must be truthfully reported
    assert check_map["desktop_smoke_verification"] in ("PASS", "UNVERIFIED")
    if check_map["desktop_smoke_verification"] == "UNVERIFIED":
        assert report.overall_status == "VALID_WITH_UNVERIFIED_DESKTOP"
        assert "UNVERIFIED" in report.desktop_verification


def test_validator_catches_invalid_references(db_session: Session, tmp_path):
    spec = build_dashboard_spec(
        title="Validator Tamper Test",
        business_purpose="Testing validation catch on invalid column reference",
        product_scope="PRD-KERENDIA",
        market_scope="MKT-CN",
    )

    gen_req = ArtifactGenerationRequest(
        spec=spec,
        actor_id="TESTER",
        force=True,
    )

    artifact = ArtifactService.generate_artifact(
        db_session,
        gen_req,
        base_export_dir=str(tmp_path),
    )

    # Tamper with report.json by injecting a completely invented non-existent column
    report_json_path = os.path.join(
        artifact.output_directory,
        "Validator_Tamper_Test.Report",
        "definition",
        "report.json"
    )
    with open(report_json_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    # Inject an invented queryRef into the first visual
    report_data["sections"][0]["visualContainers"][0]["config"]["singleVisual"]["projections"]["Values"] = [
        {"queryRef": "ProductMarketMonthly.invented_fake_column_xyz"}
    ]

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Revalidate
    report = validate_artifact(artifact.output_directory, artifact.root_pbip_file, artifact.artifact_id)
    check_map = {c.check_name: c for c in report.checks}

    assert check_map["report_reference_integrity"].status == "FAIL"
    assert "invented_fake_column_xyz" in check_map["report_reference_integrity"].details
    assert report.overall_status == "INVALID"

