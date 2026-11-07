import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.artifacts.schemas import (
    ArtifactGenerationRequest,
    ArtifactOut,
    DashboardSpecCreate,
    DashboardSpecOut,
    ValidationReport,
)
from backend.app.artifacts.service import (
    ApprovalRequiredError,
    ArtifactService,
    ReuseGateVetoError,
    SpecificationNotFoundError,
)
from backend.app.db.session import get_db

router = APIRouter(prefix="/artifacts", tags=["Power BI Artifacts"])


@router.post("/specifications", response_model=DashboardSpecOut, status_code=status.HTTP_201_CREATED)
def create_specification(
    payload: DashboardSpecCreate,
    db: Session = Depends(get_db),
):
    try:
        spec = ArtifactService.create_specification(db, payload)
        return DashboardSpecOut(
            spec_id=spec.spec_id,
            title=spec.title,
            business_purpose=spec.business_purpose,
            product_scope=spec.product_scope,
            market_scope=spec.market_scope,
            semantic_model_id=spec.semantic_model_id,
            request_id=spec.request_id,
            approval_id=spec.approval_id,
            spec_json=spec.spec_json,
            created_by=spec.created_by,
            created_at=spec.created_at,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/specifications/{spec_id}", response_model=DashboardSpecOut)
def get_specification(
    spec_id: str,
    db: Session = Depends(get_db),
):
    spec = ArtifactService.get_specification(db, spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Specification {spec_id} not found")
    return DashboardSpecOut(
        spec_id=spec.spec_id,
        title=spec.title,
        business_purpose=spec.business_purpose,
        product_scope=spec.product_scope,
        market_scope=spec.market_scope,
        semantic_model_id=spec.semantic_model_id,
        request_id=spec.request_id,
        approval_id=spec.approval_id,
        spec_json=spec.spec_json,
        created_by=spec.created_by,
        created_at=spec.created_at,
    )


@router.post("/generate", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
def generate_artifact(
    payload: ArtifactGenerationRequest,
    db: Session = Depends(get_db),
):
    try:
        artifact = ArtifactService.generate_artifact(db, payload)
        return ArtifactOut(
            artifact_id=artifact.artifact_id,
            spec_id=artifact.spec_id,
            artifact_name=artifact.artifact_name,
            format=artifact.format,
            output_directory=artifact.output_directory,
            root_pbip_file=artifact.root_pbip_file,
            status=artifact.status,
            validation_status=artifact.validation_status,
            validation_report_json=artifact.validation_report_json,
            provenance_json=artifact.provenance_json,
            generated_by=artifact.generated_by,
            created_at=artifact.created_at,
            validated_at=artifact.validated_at,
        )
    except ReuseGateVetoError as e:
        raise HTTPException(status_code=409, detail={"error": "REUSE_GATE_VETO", "message": str(e)})
    except ApprovalRequiredError as e:
        raise HTTPException(status_code=403, detail={"error": "APPROVAL_REQUIRED", "message": str(e)})
    except SpecificationNotFoundError as e:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "BAD_REQUEST", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "GENERATION_FAILED", "message": str(e)})


@router.get("", response_model=List[ArtifactOut])
def list_artifacts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    artifacts = ArtifactService.list_artifacts(db, limit=limit, offset=offset)
    return [
        ArtifactOut(
            artifact_id=a.artifact_id,
            spec_id=a.spec_id,
            artifact_name=a.artifact_name,
            format=a.format,
            output_directory=a.output_directory,
            root_pbip_file=a.root_pbip_file,
            status=a.status,
            validation_status=a.validation_status,
            validation_report_json=a.validation_report_json,
            provenance_json=a.provenance_json,
            generated_by=a.generated_by,
            created_at=a.created_at,
            validated_at=a.validated_at,
        )
        for a in artifacts
    ]


@router.get("/{artifact_id}", response_model=ArtifactOut)
def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    artifact = ArtifactService.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    return ArtifactOut(
        artifact_id=artifact.artifact_id,
        spec_id=artifact.spec_id,
        artifact_name=artifact.artifact_name,
        format=artifact.format,
        output_directory=artifact.output_directory,
        root_pbip_file=artifact.root_pbip_file,
        status=artifact.status,
        validation_status=artifact.validation_status,
        validation_report_json=artifact.validation_report_json,
        provenance_json=artifact.provenance_json,
        generated_by=artifact.generated_by,
        created_at=artifact.created_at,
        validated_at=artifact.validated_at,
    )


@router.post("/{artifact_id}/validate", response_model=ValidationReport)
def validate_artifact_endpoint(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    try:
        report = ArtifactService.revalidate_artifact(db, artifact_id)
        return report
    except SpecificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{artifact_id}/validation", response_model=ValidationReport)
def get_validation_report(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    artifact = ArtifactService.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    if not artifact.validation_report_json:
        raise HTTPException(status_code=404, detail="No validation report available for this artifact")
    data = json.loads(artifact.validation_report_json)
    return ValidationReport(**data)

