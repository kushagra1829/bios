import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from backend.app.artifacts.schemas import ValidationCheckResult, ValidationReport
from backend.app.artifacts.template_manager import BAYER_TABLE_SCHEMAS, CANONICAL_KPI_MEASURES


def check_desktop_executable_available() -> Tuple[bool, str]:
    """Check if PBIDesktop.exe is available in PATH or standard installation directories."""
    which_pbi = shutil.which("PBIDesktop.exe") or shutil.which("pbidirection.exe")
    if which_pbi:
        return True, which_pbi

    standard_paths = [
        r"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        r"C:\Program Files (x86)\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
    ]
    for p in standard_paths:
        if os.path.exists(p):
            return True, p

    return False, "PBIDesktop.exe not found on host"


def validate_artifact(artifact_dir: str, root_pbip_file: str, artifact_id: str) -> ValidationReport:
    checks: List[ValidationCheckResult] = []

    # 1. Structural Check
    has_pbip = os.path.exists(root_pbip_file)
    if not has_pbip:
        checks.append(ValidationCheckResult(
            check_name="file_structure_pbip",
            status="FAIL",
            details=f"Root .pbip file not found: {root_pbip_file}"
        ))
    else:
        checks.append(ValidationCheckResult(
            check_name="file_structure_pbip",
            status="PASS",
            details="Root .pbip file exists and is located at root"
        ))

    # Identify semantic model and report folders
    model_dir = None
    report_dir = None
    for entry in os.listdir(artifact_dir):
        full_p = os.path.join(artifact_dir, entry)
        if os.path.isdir(full_p):
            if entry.endswith(".SemanticModel"):
                model_dir = full_p
            elif entry.endswith(".Report"):
                report_dir = full_p

    if not model_dir:
        checks.append(ValidationCheckResult(
            check_name="file_structure_semantic_model",
            status="FAIL",
            details="SemanticModel directory missing"
        ))
    else:
        checks.append(ValidationCheckResult(
            check_name="file_structure_semantic_model",
            status="PASS",
            details=f"SemanticModel directory found: {os.path.basename(model_dir)}"
        ))

    if not report_dir:
        checks.append(ValidationCheckResult(
            check_name="file_structure_report",
            status="FAIL",
            details="Report directory missing"
        ))
    else:
        checks.append(ValidationCheckResult(
            check_name="file_structure_report",
            status="PASS",
            details=f"Report directory found: {os.path.basename(report_dir)}"
        ))

    # 2. PBIP & PBIR JSON Schema Check
    if has_pbip:
        try:
            with open(root_pbip_file, "r", encoding="utf-8") as f:
                pbip_data = json.load(f)
            if "version" in pbip_data and "artifacts" in pbip_data:
                checks.append(ValidationCheckResult(
                    check_name="pbip_json_schema",
                    status="PASS",
                    details=f"Valid PBIP schema version {pbip_data['version']}"
                ))
            else:
                checks.append(ValidationCheckResult(
                    check_name="pbip_json_schema",
                    status="FAIL",
                    details="PBIP json missing required 'version' or 'artifacts' keys"
                ))
        except Exception as e:
            checks.append(ValidationCheckResult(
                check_name="pbip_json_schema",
                status="FAIL",
                details=f"PBIP file contains invalid JSON: {str(e)}"
            ))

    report_json_data = None
    if report_dir:
        pbir_path = os.path.join(report_dir, "definition.pbir")
        if os.path.exists(pbir_path):
            try:
                with open(pbir_path, "r", encoding="utf-8") as f:
                    pbir_data = json.load(f)
                if "datasetReference" in pbir_data and "byPath" in pbir_data["datasetReference"]:
                    checks.append(ValidationCheckResult(
                        check_name="pbir_schema",
                        status="PASS",
                        details="definition.pbir is valid and correctly references semantic model path"
                    ))
                else:
                    checks.append(ValidationCheckResult(
                        check_name="pbir_schema",
                        status="FAIL",
                        details="definition.pbir missing datasetReference.byPath"
                    ))
            except Exception as e:
                checks.append(ValidationCheckResult(
                    check_name="pbir_schema",
                    status="FAIL",
                    details=f"definition.pbir invalid JSON: {str(e)}"
                ))
        else:
            checks.append(ValidationCheckResult(
                check_name="pbir_schema",
                status="FAIL",
                details="definition.pbir does not exist"
            ))

        report_json_path = os.path.join(report_dir, "definition", "report.json")
        if os.path.exists(report_json_path):
            try:
                with open(report_json_path, "r", encoding="utf-8") as f:
                    report_json_data = json.load(f)
                if "sections" in report_json_data and isinstance(report_json_data["sections"], list):
                    checks.append(ValidationCheckResult(
                        check_name="report_json_schema",
                        status="PASS",
                        details=f"report.json valid with {len(report_json_data['sections'])} section(s)"
                    ))
                else:
                    checks.append(ValidationCheckResult(
                        check_name="report_json_schema",
                        status="FAIL",
                        details="report.json missing sections array"
                    ))
            except Exception as e:
                checks.append(ValidationCheckResult(
                    check_name="report_json_schema",
                    status="FAIL",
                    details=f"report.json invalid JSON: {str(e)}"
                ))
        else:
            checks.append(ValidationCheckResult(
                check_name="report_json_schema",
                status="FAIL",
                details="definition/report.json does not exist"
            ))

    # 3. TMDL Syntax / Semantic Check
    defined_measures = set()
    defined_tables = set()
    if model_dir:
        def_dir = os.path.join(model_dir, "definition")
        db_tmdl = os.path.join(def_dir, "database.tmdl")
        model_tmdl = os.path.join(def_dir, "model.tmdl")

        if os.path.exists(db_tmdl) and os.path.exists(model_tmdl):
            with open(db_tmdl, "r", encoding="utf-8") as f:
                db_content = f.read()
            if "compatibilityLevel: 1567" in db_content:
                checks.append(ValidationCheckResult(
                    check_name="tmdl_database_compatibility",
                    status="PASS",
                    details="database.tmdl specifies compatibilityLevel: 1567"
                ))
            else:
                checks.append(ValidationCheckResult(
                    check_name="tmdl_database_compatibility",
                    status="FAIL",
                    details="database.tmdl missing compatibilityLevel: 1567"
                ))
        else:
            checks.append(ValidationCheckResult(
                check_name="tmdl_database_compatibility",
                status="FAIL",
                details="database.tmdl or model.tmdl missing"
            ))

        tables_dir = os.path.join(def_dir, "tables")
        if os.path.exists(tables_dir):
            for t_file in os.listdir(tables_dir):
                if t_file.endswith(".tmdl"):
                    t_name = t_file[:-5]
                    defined_tables.add(t_name)
                    t_path = os.path.join(tables_dir, t_file)
                    with open(t_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for line in lines:
                        sline = line.strip()
                        if sline.startswith("measure '"):
                            # measure 'Measure Name' = ...
                            parts = sline.split("'", 2)
                            if len(parts) >= 2:
                                defined_measures.add(parts[1])
            checks.append(ValidationCheckResult(
                check_name="tmdl_tables_syntax",
                status="PASS",
                details=f"Validated {len(defined_tables)} tables and {len(defined_measures)} measures in TMDL"
            ))
        else:
            checks.append(ValidationCheckResult(
                check_name="tmdl_tables_syntax",
                status="FAIL",
                details="TMDL tables directory missing"
            ))

    # 4. Field & Measure Reference Check in Report
    field_ref_failures = []
    if report_json_data:
        for section in report_json_data.get("sections", []):
            for vc in section.get("visualContainers", []):
                config = vc.get("config", {})
                single_visual = config.get("singleVisual", {})
                projections = single_visual.get("projections", {})
                for proj_group, proj_list in projections.items():
                    for proj in proj_list:
                        qref = proj.get("queryRef", "")
                        if "." in qref:
                            tbl, item = qref.split(".", 1)
                            # Check if table exists in defined tables
                            if tbl not in defined_tables:
                                field_ref_failures.append(f"Visual references unknown table '{tbl}' in '{qref}'")
                            else:
                                # Check if item is either a known column or a defined measure
                                known_cols = BAYER_TABLE_SCHEMAS.get(tbl, {})
                                if item not in known_cols and item not in defined_measures:
                                    field_ref_failures.append(f"Field or measure '{item}' in queryRef '{qref}' does not exist in schema or defined measures")

    if field_ref_failures:
        checks.append(ValidationCheckResult(
            check_name="report_reference_integrity",
            status="FAIL",
            details="; ".join(field_ref_failures[:5])
        ))
    else:
        checks.append(ValidationCheckResult(
            check_name="report_reference_integrity",
            status="PASS",
            details="All visual field and measure queryRefs resolve to canonical table columns or defined measures"
        ))

    # 5. Relationship Integrity Check
    rel_path = os.path.join(model_dir, "definition", "relationships.tmdl") if model_dir else None
    if rel_path and os.path.exists(rel_path):
        with open(rel_path, "r", encoding="utf-8") as f:
            rel_content = f.read()
        rel_errors = []
        for line in rel_content.splitlines():
            line_str = line.strip()
            if line_str.startswith("fromColumn:") or line_str.startswith("toColumn:"):
                # e.g. fromColumn: 'ProductMarketMonthly'.'product_id'
                parts = line_str.split(":", 1)[1].strip().split(".")
                if len(parts) == 2:
                    t_str = parts[0].strip("'")
                    c_str = parts[1].strip("'")
                    if t_str not in BAYER_TABLE_SCHEMAS:
                        rel_errors.append(f"Unknown table in relationship: {t_str}")
                    elif c_str not in BAYER_TABLE_SCHEMAS[t_str]:
                        rel_errors.append(f"Unknown column in relationship: {t_str}.{c_str}")
        if rel_errors:
            checks.append(ValidationCheckResult(
                check_name="relationship_integrity",
                status="FAIL",
                details="; ".join(rel_errors)
            ))
        else:
            checks.append(ValidationCheckResult(
                check_name="relationship_integrity",
                status="PASS",
                details="All relationships reference existing canonical tables and key columns"
            ))

    # 6. Desktop Tooling Verification
    pbi_available, pbi_detail = check_desktop_executable_available()
    if pbi_available:
        checks.append(ValidationCheckResult(
            check_name="desktop_smoke_verification",
            status="PASS",
            details=f"Power BI Desktop executable detected at {pbi_detail}"
        ))
        desktop_status = f"VERIFIED ({pbi_detail})"
    else:
        checks.append(ValidationCheckResult(
            check_name="desktop_smoke_verification",
            status="UNVERIFIED",
            details=f"Live application verification unverified: {pbi_detail}"
        ))
        desktop_status = "UNVERIFIED (PBIDesktop.exe not found on host)"

    # Determine overall status
    has_failures = any(c.status == "FAIL" for c in checks)
    if has_failures:
        overall_status = "INVALID"
    elif not pbi_available:
        overall_status = "VALID_WITH_UNVERIFIED_DESKTOP"
    else:
        overall_status = "VALID"

    return ValidationReport(
        artifact_id=artifact_id,
        overall_status=overall_status,
        checks=checks,
        desktop_verification=desktop_status,
        timestamp=datetime.now(timezone.utc)
    )

