from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from backend.app.db.session import get_db
from backend.app.models.audit import SourceImportRuns
from backend.app.schemas.catalog import IngestionReportOut
from backend.app.ingestion.loader import WorkbookIngestionService

router = APIRouter()


@router.post("/run", response_model=IngestionReportOut)
def run_ingestion(
    dry_run: bool = Query(False, description="Simulate ingestion without writing to database"),
):
    service = WorkbookIngestionService()
    try:
        report = service.ingest_workbook(dry_run=dry_run)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion run failed: {str(e)}",
        )


@router.get("/status", response_model=Optional[dict])
def get_latest_ingestion_status(db: Session = Depends(get_db)):
    latest_run = db.execute(
        select(SourceImportRuns).order_by(desc(SourceImportRuns.started_at)).limit(1)
    ).scalar_one_or_none()

    if not latest_run:
        return {"message": "No ingestion runs recorded yet."}

    return {
        "import_id": latest_run.import_id,
        "source_filename": latest_run.source_filename,
        "file_sha256": latest_run.file_sha256,
        "workbook_version": latest_run.workbook_version,
        "total_records_processed": latest_run.total_records_processed,
        "status": latest_run.status,
        "error_message": latest_run.error_message,
        "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
        "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
    }

