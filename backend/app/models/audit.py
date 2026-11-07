from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Index
from backend.app.db.session import Base


class SourceImportRuns(Base):
    __tablename__ = "source_import_runs"

    import_id = Column(String(50), primary_key=True)
    source_filename = Column(String(255), nullable=False)
    file_sha256 = Column(String(64), nullable=False, index=True)
    workbook_version = Column(String(20), nullable=False, default="2.0")
    total_records_processed = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="in_progress")  # success, failed, dry_run
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class StagingWorkbookRaw(Base):
    __tablename__ = "staging_workbook_raw"

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_id = Column(String(50), ForeignKey("source_import_runs.import_id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_name = Column(String(50), nullable=False, index=True)
    row_index = Column(Integer, nullable=False)
    record_key = Column(String(100), nullable=True, index=True)
    raw_json = Column(Text, nullable=False)
    record_hash = Column(String(64), nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)
    validation_error = Column(Text, nullable=True)
    imported_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_staging_sheet_key", "sheet_name", "record_key"),
    )

