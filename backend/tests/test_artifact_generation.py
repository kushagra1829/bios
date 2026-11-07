import json
import os
import pytest
from sqlalchemy.orm import Session

from backend.app.artifacts.schemas import ArtifactGenerationRequest
from backend.app.artifacts.service import ArtifactService
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.db.session import SessionLocal
from backend.app.models.approval import AuditEvents
from backend.app.models.artifact import GeneratedArtifacts


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_generate_pbip_project_complete(db_session: Session, tmp_path):
    spec = build_dashboard_spec(
        title="Kerendia Global Launch Tracker",
        business_purpose="Track monthly net sales and forecast variance across markets",
        product_scope="PRD-KERENDIA",
        market_scope="GLOBAL",
    )

    gen_req = ArtifactGenerationRequest(
        spec=spec,
        actor_id="DEVELOPER-1",
        actor_role="BI_DEVELOPER",
        force=True,
    )

    artifact = ArtifactService.generate_artifact(
        db_session,
        gen_req,
        base_export_dir=str(tmp_path),
    )

    assert artifact.artifact_id.startswith("ART-")
    assert artifact.artifact_name == "Kerendia_Global_Launch_Tracker"
    assert os.path.exists(artifact.output_directory)

    # 1. Root .pbip
    assert os.path.exists(artifact.root_pbip_file)
    with open(artifact.root_pbip_file, "r", encoding="utf-8") as f:
        pbip_data = json.load(f)
    assert pbip_data["version"] == "1.0"
    assert pbip_data["artifacts"][0]["report"]["path"] == "Kerendia_Global_Launch_Tracker.Report"

    # 2. Semantic Model folder & files
    model_dir = os.path.join(artifact.output_directory, "Kerendia_Global_Launch_Tracker.SemanticModel")
    assert os.path.isdir(model_dir)

    pbidataset_path = os.path.join(model_dir, "definition.pbidataset")
    assert os.path.exists(pbidataset_path)

    db_tmdl = os.path.join(model_dir, "definition", "database.tmdl")
    assert os.path.exists(db_tmdl)
    with open(db_tmdl, "r", encoding="utf-8") as f:
        content = f.read()
    assert "compatibilityLevel: 1567" in content

    model_tmdl = os.path.join(model_dir, "definition", "model.tmdl")
    assert os.path.exists(model_tmdl)
    with open(model_tmdl, "r", encoding="utf-8") as f:
        content = f.read()
    assert "powerBI_V3" in content

    # Table TMDLs
    for tbl in spec.tables:
        t_path = os.path.join(model_dir, "definition", "tables", f"{tbl}.tmdl")
        assert os.path.exists(t_path), f"Table TMDL {t_path} missing"

    # Relationships TMDL
    rel_path = os.path.join(model_dir, "definition", "relationships.tmdl")
    assert os.path.exists(rel_path)
    with open(rel_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "ProductMarketMonthly" in content
    assert "Products" in content

    # 3. Report folder & files
    report_dir = os.path.join(artifact.output_directory, "Kerendia_Global_Launch_Tracker.Report")
    assert os.path.isdir(report_dir)

    pbir_path = os.path.join(report_dir, "definition.pbir")
    assert os.path.exists(pbir_path)
    with open(pbir_path, "r", encoding="utf-8") as f:
        pbir_data = json.load(f)
    assert pbir_data["datasetReference"]["byPath"]["path"] == "../Kerendia_Global_Launch_Tracker.SemanticModel"

    report_json_path = os.path.join(report_dir, "definition", "report.json")
    assert os.path.exists(report_json_path)
    with open(report_json_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    assert len(report_data["sections"]) >= 1
    # Check theme tokens
    custom_theme = report_data["themeCollection"]["customTheme"]
    assert "#142438" in custom_theme["dataColors"]  # Midnight
    assert "#3478F6" in custom_theme["dataColors"]  # Intelligence Blue

    # 4. Provenance
    prov = json.loads(artifact.provenance_json)
    assert "spec_hash" in prov
    assert prov["file_count"] >= 7
    assert "file_manifest" in prov

    # 5. Audit Event
    audit = db_session.query(AuditEvents).filter(
        AuditEvents.target_entity_id == artifact.artifact_id,
        AuditEvents.event_type == "ARTIFACT_GENERATED",
    ).first()
    assert audit is not None
    assert audit.actor_id == "DEVELOPER-1"
    assert audit.action == "GENERATE_POWERBI_PROJECT"

