import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.artifacts.pbir_generator import generate_report_files
from backend.app.artifacts.provenance import build_artifact_provenance
from backend.app.artifacts.schemas import (
    ArtifactGenerationRequest,
    DashboardSpec,
    DashboardSpecCreate,
    ValidationReport,
)
from backend.app.artifacts.spec_builder import build_dashboard_spec
from backend.app.artifacts.tmdl_generator import generate_semantic_model_files
from backend.app.artifacts.validator import validate_artifact
from backend.app.models.approval import ApprovalRequests, AuditEvents
from backend.app.models.artifact import DashboardSpecifications, GeneratedArtifacts
from backend.app.models.assistant import AssistantRecommendations, AssistantRequests


class ReuseGateVetoError(Exception):
    """Raised when the reuse-first gate vetoes dashboard generation."""
    pass


class ApprovalRequiredError(Exception):
    """Raised when an approval is required for BUILD_NEW action."""
    pass


class SpecificationNotFoundError(Exception):
    """Raised when a dashboard specification is not found."""
    pass


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^\w\-_]", "_", name)


class ArtifactService:
    @staticmethod
    def create_specification(
        db: Session,
        spec_create: DashboardSpecCreate,
        created_by: str = "SYSTEM_FACTORY",
    ) -> DashboardSpecifications:
        spec = build_dashboard_spec(
            title=spec_create.title,
            business_purpose=spec_create.business_purpose,
            product_scope=spec_create.product_scope,
            market_scope=spec_create.market_scope,
            semantic_model_id=spec_create.semantic_model_id,
            request_id=spec_create.request_id,
            approval_id=spec_create.approval_id,
            kpi_ids=spec_create.kpi_ids,
        )

        db_spec = DashboardSpecifications(
            spec_id=spec.spec_id,
            title=spec.title,
            business_purpose=spec.business_purpose,
            request_id=spec.request_id,
            approval_id=spec.approval_id,
            product_scope=spec.product_scope,
            market_scope=spec.market_scope,
            semantic_model_id=spec.semantic_model_id,
            spec_json=json.dumps(spec.model_dump(), indent=2),
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_spec)
        db.commit()
        db.refresh(db_spec)
        return db_spec

    @staticmethod
    def get_specification(db: Session, spec_id: str) -> Optional[DashboardSpecifications]:
        return db.query(DashboardSpecifications).filter(DashboardSpecifications.spec_id == spec_id).first()

    @staticmethod
    def generate_artifact(
        db: Session,
        request: ArtifactGenerationRequest,
        base_export_dir: str = "data/exports/powerbi",
    ) -> GeneratedArtifacts:
        # 1. Resolve specification
        spec: Optional[DashboardSpec] = None
        db_spec: Optional[DashboardSpecifications] = None

        if request.spec:
            spec = request.spec
        elif request.spec_id:
            db_spec = db.query(DashboardSpecifications).filter(
                DashboardSpecifications.spec_id == request.spec_id
            ).first()
            if not db_spec:
                raise SpecificationNotFoundError(f"Specification {request.spec_id} not found")
            spec = DashboardSpec(**json.loads(db_spec.spec_json))
        elif request.request_id:
            # Build spec from request details
            assistant_req = db.query(AssistantRequests).filter(
                AssistantRequests.request_id == request.request_id
            ).first()
            if not assistant_req:
                raise SpecificationNotFoundError(f"Assistant request {request.request_id} not found")
            spec = build_dashboard_spec(
                title=f"Dashboard for Request {request.request_id}",
                business_purpose=assistant_req.raw_prompt,
                product_scope="GLOBAL",
                market_scope="GLOBAL",
                request_id=request.request_id,
                approval_id=request.approval_id,
            )
        else:
            raise ValueError("Either spec, spec_id, or request_id must be provided")

        # 2. Enforce Reuse-First Gate & Synchronous Approval Verification
        req_id = spec.request_id or request.request_id
        from backend.app.approvals.service import ApprovalService

        # Explicit approval provided on spec or request must be verified synchronously
        explicit_app_id = spec.approval_id or request.approval_id
        if explicit_app_id and not request.force:
            try:
                ApprovalService.verify_waiver_synchronous(
                    db=db,
                    waiver_id=explicit_app_id,
                )
            except (PermissionError, ValueError) as err:
                raise ApprovalRequiredError(f"APPROVAL_REQUIRED: {err}")

        if req_id and not request.force:
            rec = db.query(AssistantRecommendations).filter(
                AssistantRecommendations.request_id == req_id
            ).first()
            if rec:
                decision = rec.decision.upper()
                if decision in ("REUSE", "CONSOLIDATE", "MODIFY"):
                    raise ReuseGateVetoError(
                        f"REUSE_GATE_VETO: Recommended action is {decision}. Direct generation of a new dashboard "
                        f"is prohibited under Bayer Governance Rule RULE-001. Existing analytics asset should be reused or consolidated."
                    )
                if decision == "BUILD_NEW":
                    # Check if human approval exists and is approved
                    app_id = spec.approval_id or request.approval_id
                    if not app_id:
                        # Search for matching approval request
                        app = db.query(ApprovalRequests).filter(
                            ApprovalRequests.target_entity_id == req_id,
                            ApprovalRequests.status == "APPROVED"
                        ).first()
                        if not app:
                            raise ApprovalRequiredError(
                                "APPROVAL_REQUIRED: Action BUILD_NEW requires an approved human approval before artifact generation."
                            )
                        try:
                            ApprovalService.verify_waiver_synchronous(
                                db=db,
                                waiver_id=app.approval_id,
                                target_entity_id=req_id,
                            )
                        except (PermissionError, ValueError) as err:
                            raise ApprovalRequiredError(f"APPROVAL_REQUIRED: {err}")
                    else:
                        app = db.query(ApprovalRequests).filter(
                            ApprovalRequests.approval_id == app_id
                        ).first()
                        if not app:
                            raise ApprovalRequiredError(
                                f"APPROVAL_REQUIRED: Approval {app_id} is not found."
                            )
                        try:
                            ApprovalService.verify_waiver_synchronous(
                                db=db,
                                waiver_id=app.approval_id,
                            )
                        except (PermissionError, ValueError) as err:
                            raise ApprovalRequiredError(f"APPROVAL_REQUIRED: {err}")

        # 3. Create or save specification in DB if not already present
        if not db_spec:
            db_spec = db.query(DashboardSpecifications).filter(
                DashboardSpecifications.spec_id == spec.spec_id
            ).first()
            if not db_spec:
                db_spec = DashboardSpecifications(
                    spec_id=spec.spec_id,
                    title=spec.title,
                    business_purpose=spec.business_purpose,
                    request_id=spec.request_id,
                    approval_id=spec.approval_id,
                    product_scope=spec.product_scope,
                    market_scope=spec.market_scope,
                    semantic_model_id=spec.semantic_model_id,
                    spec_json=json.dumps(spec.model_dump(), indent=2),
                    created_by=request.actor_id,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(db_spec)
                db.commit()

        # 4. Determine Project Paths
        artifact_id = f"ART-{uuid.uuid4().hex[:8].upper()}"
        safe_name = _sanitize_filename(spec.title)
        project_folder_name = f"{safe_name}_{spec.spec_id}"
        artifact_dir = os.path.abspath(os.path.join(base_export_dir, project_folder_name))
        os.makedirs(artifact_dir, exist_ok=True)

        semantic_model_folder_name = f"{safe_name}.SemanticModel"
        semantic_model_dir = os.path.join(artifact_dir, semantic_model_folder_name)
        report_folder_name = f"{safe_name}.Report"
        report_dir = os.path.join(artifact_dir, report_folder_name)

        # 5. Generate Root .pbip File
        root_pbip_file = os.path.join(artifact_dir, f"{safe_name}.pbip")
        pbip_content = {
            "version": "1.0",
            "artifacts": [
                {
                    "report": {
                        "path": report_folder_name
                    }
                }
            ]
        }
        with open(root_pbip_file, "w", encoding="utf-8") as f:
            json.dump(pbip_content, f, indent=2)

        generated_files: Dict[str, str] = {
            f"{safe_name}.pbip": root_pbip_file
        }

        # 6. Generate TMDL Semantic Model
        model_files = generate_semantic_model_files(spec, semantic_model_dir)
        for rel_k, abs_v in model_files.items():
            generated_files[f"{semantic_model_folder_name}/{rel_k}"] = abs_v

        # 7. Generate PBIR Report Definition
        report_files = generate_report_files(spec, report_dir, semantic_model_folder_name)
        for rel_k, abs_v in report_files.items():
            generated_files[f"{report_folder_name}/{rel_k}"] = abs_v

        # 8. Compute Provenance
        provenance = build_artifact_provenance(
            spec_dict=spec.model_dump(),
            generated_files=generated_files,
        )

        # 9. Perform Validation
        validation_report = validate_artifact(artifact_dir, root_pbip_file, artifact_id)

        # 10. Persist GeneratedArtifacts Record
        val_status = "valid" if validation_report.overall_status in ("VALID", "VALID_WITH_UNVERIFIED_DESKTOP") else "invalid"
        gen_status = "validated" if val_status == "valid" else "validation_failed"

        db_artifact = GeneratedArtifacts(
            artifact_id=artifact_id,
            spec_id=spec.spec_id,
            artifact_name=safe_name,
            format=request.output_format,
            output_directory=artifact_dir,
            root_pbip_file=root_pbip_file,
            status=gen_status,
            provenance_json=json.dumps(provenance, indent=2),
            validation_status=val_status,
            validation_report_json=json.dumps(validation_report.model_dump(), default=str, indent=2),
            generated_by=request.actor_id,
            created_at=datetime.now(timezone.utc),
            validated_at=datetime.now(timezone.utc),
        )
        db.add(db_artifact)

        # 11. Create Audit Event
        audit_event = AuditEvents(
            event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
            actor_id=request.actor_id,
            actor_role=request.actor_role,
            event_type="ARTIFACT_GENERATED",
            target_entity_type="artifact",
            target_entity_id=artifact_id,
            action="GENERATE_POWERBI_PROJECT",
            before_state_json=None,
            after_state_json=json.dumps({
                "status": gen_status,
                "validation_status": val_status,
                "project_path": artifact_dir,
            }),
            reason=f"Generated Power BI PBIP project for spec {spec.spec_id} ({spec.title})",
            associated_recommendation_id=rec.recommendation_id if (req_id and 'rec' in locals() and rec) else None,
            provenance_json=json.dumps({
                "spec_id": spec.spec_id,
                "files_count": len(generated_files),
                "validation_overall": validation_report.overall_status,
            }),
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_event)

        db.commit()
        db.refresh(db_artifact)
        return db_artifact

    @staticmethod
    def revalidate_artifact(db: Session, artifact_id: str) -> ValidationReport:
        artifact = db.query(GeneratedArtifacts).filter(
            GeneratedArtifacts.artifact_id == artifact_id
        ).first()
        if not artifact:
            raise SpecificationNotFoundError(f"Artifact {artifact_id} not found")

        report = validate_artifact(artifact.output_directory, artifact.root_pbip_file, artifact_id)
        val_status = "valid" if report.overall_status in ("VALID", "VALID_WITH_UNVERIFIED_DESKTOP") else "invalid"
        gen_status = "validated" if val_status == "valid" else "validation_failed"

        artifact.validation_status = val_status
        artifact.status = gen_status
        artifact.validation_report_json = json.dumps(report.model_dump(), default=str, indent=2)
        artifact.validated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(artifact)
        return report

    @staticmethod
    def list_artifacts(db: Session, limit: int = 50, offset: int = 0) -> List[GeneratedArtifacts]:
        return db.query(GeneratedArtifacts).order_by(GeneratedArtifacts.created_at.desc()).offset(offset).limit(limit).all()

    @staticmethod
    def get_artifact(db: Session, artifact_id: str) -> Optional[GeneratedArtifacts]:
        return db.query(GeneratedArtifacts).filter(GeneratedArtifacts.artifact_id == artifact_id).first()

