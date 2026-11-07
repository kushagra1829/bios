import hashlib
import json
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import openpyxl

from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.db.session import SessionLocal, WORKSPACE_ROOT
from backend.app.models.audit import SourceImportRuns, StagingWorkbookRaw
from backend.app.models.core import (
    Workspaces,
    Owners,
    SemanticModels,
    AnalyticsAssets,
    AssetUsage,
    LineageEdges,
)
from backend.app.models.governance import (
    KpiCatalog,
    AssetKpiMap,
    GovernanceSignals,
    MigrationBacklog,
    DataQuality,
    GovernanceRules,
    BusinessRequests,
)
from backend.app.models.domain import (
    Products,
    Markets,
    ProductMarketMonthly,
    LaunchMilestones,
    MarketAccess,
    SupplyOperations,
)

logger = logging.getLogger("bios.ingestion")

DEFAULT_WORKBOOK_PATH = WORKSPACE_ROOT / "data" / "source" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"

REQUIRED_SHEETS = [
    "Workspaces",
    "Owners",
    "Products",
    "Markets",
    "Governance_Rules",
    "Business_Requests",
    "Semantic_Models",
    "KPI_Catalog",
    "Analytics_Assets",
    "Asset_KPI_Map",
    "Asset_Usage",
    "Lineage_Edges",
    "Product_Market_Monthly",
    "Launch_Milestones",
    "Market_Access",
    "Supply_Operations",
    "Data_Quality",
    "Governance_Signals",
    "Migration_Backlog",
]

DOCS_METADATA_SHEETS = [
    "START_HERE",
    "Public_References",
    "Data_Dictionary",
    "Package_Overview",
    "Change_Log",
]


def compute_file_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_dict_hash(d: Dict[str, Any]) -> str:
    serialized = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_datetime(val: Any) -> Optional[datetime]:
    if val is None or str(val).strip() == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    try:
        return datetime.fromisoformat(str(val).strip())
    except Exception:
        return None


def parse_float(val: Any) -> Optional[float]:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_int(val: Any, default: int = 0) -> int:
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def parse_bool(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


class IngestionReport:
    def __init__(self, import_id: str, file_path: str, file_hash: str, dry_run: bool):
        self.import_id = import_id
        self.file_path = file_path
        self.file_hash = file_hash
        self.dry_run = dry_run
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.status = "in_progress"
        self.total_records = 0
        self.total_inserted = 0
        self.total_updated = 0
        self.total_unchanged = 0
        self.total_rejected = 0
        self.sheet_stats: Dict[str, Dict[str, int]] = {}
        self.validation_errors: List[Dict[str, Any]] = []

    def init_sheet(self, sheet: str):
        if sheet not in self.sheet_stats:
            self.sheet_stats[sheet] = {
                "total": 0,
                "inserted": 0,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
            }

    def record_row(self, sheet: str, action: str):
        self.init_sheet(sheet)
        self.sheet_stats[sheet]["total"] += 1
        self.total_records += 1
        if action == "inserted":
            self.sheet_stats[sheet]["inserted"] += 1
            self.total_inserted += 1
        elif action == "updated":
            self.sheet_stats[sheet]["updated"] += 1
            self.total_updated += 1
        elif action == "unchanged":
            self.sheet_stats[sheet]["unchanged"] += 1
            self.total_unchanged += 1
        elif action == "rejected":
            self.sheet_stats[sheet]["rejected"] += 1
            self.total_rejected += 1

    def add_error(self, sheet: str, row_index: int, record_key: Optional[str], message: str):
        self.validation_errors.append({
            "sheet": sheet,
            "row_index": row_index,
            "record_key": record_key,
            "error": message,
        })
        self.record_row(sheet, "rejected")

    def finalize(self, success: bool, error_msg: Optional[str] = None):
        self.completed_at = datetime.now(timezone.utc)
        if error_msg:
            self.status = "failed"
        elif self.dry_run:
            self.status = "dry_run"
        else:
            self.status = "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "dry_run": self.dry_run,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_records": self.total_records,
            "total_inserted": self.total_inserted,
            "total_updated": self.total_updated,
            "total_unchanged": self.total_unchanged,
            "total_rejected": self.total_rejected,
            "sheet_stats": self.sheet_stats,
            "validation_errors_count": len(self.validation_errors),
            "sample_errors": self.validation_errors[:10],
        }


class WorkbookIngestionService:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def ingest_workbook(
        self,
        workbook_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> IngestionReport:
        target_path = Path(workbook_path or DEFAULT_WORKBOOK_PATH).resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Source workbook not found at: {target_path}")

        file_hash = compute_file_sha256(target_path)
        import_id = f"IMP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file_hash[:8]}"
        report = IngestionReport(import_id, str(target_path), file_hash, dry_run)

        logger.info(f"Starting ingestion run {import_id} (dry_run={dry_run}) from {target_path}")

        wb = openpyxl.load_workbook(target_path, data_only=True)

        # Validate required sheets exist
        missing_sheets = [s for s in REQUIRED_SHEETS if s not in wb.sheetnames]
        if missing_sheets:
            err = f"Workbook missing required worksheets: {missing_sheets}"
            report.finalize(False, err)
            raise ValueError(err)

        session: Session = self.session_factory()
        try:
            # Record import run
            import_record = SourceImportRuns(
                import_id=import_id,
                source_filename=target_path.name,
                file_sha256=file_hash,
                workbook_version="2.0",
                total_records_processed=0,
                status="dry_run" if dry_run else "in_progress",
                started_at=datetime.now(timezone.utc),
            )
            if not dry_run:
                session.add(import_record)
                session.flush()

            # Process in strict dependency order
            self._ingest_workspaces(session, wb["Workspaces"], report, import_id, dry_run)
            self._ingest_owners(session, wb["Owners"], report, import_id, dry_run)
            self._ingest_products(session, wb["Products"], report, import_id, dry_run)
            self._ingest_markets(session, wb["Markets"], report, import_id, dry_run)
            self._ingest_governance_rules(session, wb["Governance_Rules"], report, import_id, dry_run)
            self._ingest_business_requests(session, wb["Business_Requests"], report, import_id, dry_run)
            self._ingest_semantic_models(session, wb["Semantic_Models"], report, import_id, dry_run)
            self._ingest_kpi_catalog(session, wb["KPI_Catalog"], report, import_id, dry_run)
            self._ingest_analytics_assets(session, wb["Analytics_Assets"], report, import_id, dry_run)
            self._ingest_asset_kpi_map(session, wb["Asset_KPI_Map"], report, import_id, dry_run)
            self._ingest_asset_usage(session, wb["Asset_Usage"], report, import_id, dry_run)
            self._ingest_lineage_edges(session, wb["Lineage_Edges"], report, import_id, dry_run)
            self._ingest_product_market_monthly(session, wb["Product_Market_Monthly"], report, import_id, dry_run)
            self._ingest_launch_milestones(session, wb["Launch_Milestones"], report, import_id, dry_run)
            self._ingest_market_access(session, wb["Market_Access"], report, import_id, dry_run)
            self._ingest_supply_operations(session, wb["Supply_Operations"], report, import_id, dry_run)
            self._ingest_data_quality(session, wb["Data_Quality"], report, import_id, dry_run)
            self._ingest_governance_signals(session, wb["Governance_Signals"], report, import_id, dry_run)
            self._ingest_migration_backlog(session, wb["Migration_Backlog"], report, import_id, dry_run)
            self._ingest_documentation_sheets(session, wb, report, import_id, dry_run)

            if dry_run:
                session.rollback()
                report.finalize(True)
            else:
                import_record.total_records_processed = report.total_records
                import_record.status = "success"
                import_record.completed_at = datetime.now(timezone.utc)
                session.commit()
                report.finalize(True)

            logger.info(f"Ingestion {import_id} complete. Total records: {report.total_records}, Inserted: {report.total_inserted}, Unchanged: {report.total_unchanged}")
            return report

        except Exception as e:
            session.rollback()
            report.finalize(False, str(e))
            logger.error(f"Ingestion run {import_id} failed: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def _read_sheet_records(self, ws) -> List[Tuple[int, Dict[str, Any]]]:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
        records = []
        for row_idx, r in enumerate(rows[1:], start=2):
            if any(c is not None and str(c).strip() != "" for c in r):
                row_dict = dict(zip(headers, r[:len(headers)]))
                records.append((row_idx, row_dict))
        return records

    def _save_staging(
        self,
        session: Session,
        import_id: str,
        sheet: str,
        row_idx: int,
        record_key: Optional[str],
        data: Dict[str, Any],
        is_valid: bool = True,
        error_msg: Optional[str] = None,
        dry_run: bool = False,
    ):
        if dry_run:
            return
        rec_hash = compute_dict_hash(data)
        staging = StagingWorkbookRaw(
            import_id=import_id,
            sheet_name=sheet,
            row_index=row_idx,
            record_key=record_key,
            raw_json=json.dumps(data, default=str),
            record_hash=rec_hash,
            is_valid=is_valid,
            validation_error=error_msg,
            imported_at=datetime.now(timezone.utc),
        )
        session.add(staging)

    # 1. Workspaces
    def _ingest_workspaces(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Workspaces"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)

        existing = {w.workspace_id: w for w in session.execute(select(Workspaces)).scalars().all()}

        for row_idx, r in records:
            wid = str(r.get("workspace_id") or "").strip()
            if not wid:
                report.add_error(sheet, row_idx, None, "Missing workspace_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, wid, r, dry_run=dry_run)

            if wid in existing:
                item = existing[wid]
                changed = (
                    item.workspace_name != str(r.get("workspace_name"))
                    or item.scope != str(r.get("scope"))
                    or item.environment != str(r.get("environment"))
                    or item.governance_mode != str(r.get("governance_mode"))
                    or item.classification != str(r.get("classification"))
                )
                if changed:
                    item.workspace_name = str(r.get("workspace_name"))
                    item.scope = str(r.get("scope"))
                    item.environment = str(r.get("environment"))
                    item.platform = str(r.get("platform") or "Power BI")
                    item.governance_mode = str(r.get("governance_mode"))
                    item.classification = str(r.get("classification"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = Workspaces(
                    workspace_id=wid,
                    workspace_name=str(r.get("workspace_name")),
                    scope=str(r.get("scope")),
                    environment=str(r.get("environment")),
                    platform=str(r.get("platform") or "Power BI"),
                    governance_mode=str(r.get("governance_mode")),
                    classification=str(r.get("classification")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[wid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 2. Owners
    def _ingest_owners(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Owners"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {o.owner_id: o for o in session.execute(select(Owners)).scalars().all()}

        for row_idx, r in records:
            oid = str(r.get("owner_id") or "").strip()
            if not oid:
                report.add_error(sheet, row_idx, None, "Missing owner_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, oid, r, dry_run=dry_run)

            if oid in existing:
                item = existing[oid]
                changed = (
                    item.owner_name != str(r.get("owner_name"))
                    or item.role != str(r.get("role"))
                    or item.status != str(r.get("status"))
                )
                if changed:
                    item.owner_name = str(r.get("owner_name"))
                    item.role = str(r.get("role"))
                    item.scope = str(r.get("scope"))
                    item.status = str(r.get("status"))
                    item.email = str(r.get("email"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = Owners(
                    owner_id=oid,
                    owner_name=str(r.get("owner_name")),
                    role=str(r.get("role")),
                    scope=str(r.get("scope")),
                    status=str(r.get("status")),
                    email=str(r.get("email")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[oid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 3. Products
    def _ingest_products(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Products"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {p.product_id: p for p in session.execute(select(Products)).scalars().all()}

        for row_idx, r in records:
            pid = str(r.get("product_id") or "").strip()
            if not pid:
                report.add_error(sheet, row_idx, None, "Missing product_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, pid, r, dry_run=dry_run)

            if pid in existing:
                item = existing[pid]
                if item.product_name != str(r.get("product_name")):
                    item.product_name = str(r.get("product_name"))
                    item.therapeutic_area = str(r.get("therapeutic_area"))
                    item.product_type = str(r.get("product_type"))
                    item.portfolio_stage = str(r.get("portfolio_stage"))
                    item.commercial_scope = str(r.get("commercial_scope"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = Products(
                    product_id=pid,
                    product_name=str(r.get("product_name")),
                    therapeutic_area=str(r.get("therapeutic_area")),
                    product_type=str(r.get("product_type")),
                    portfolio_stage=str(r.get("portfolio_stage")),
                    commercial_scope=str(r.get("commercial_scope")),
                    public_context_only=parse_bool(r.get("public_context_only"), True),
                )
                session.add(item)
                existing[pid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 4. Markets
    def _ingest_markets(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Markets"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {m.market_id: m for m in session.execute(select(Markets)).scalars().all()}

        for row_idx, r in records:
            mid = str(r.get("market_id") or "").strip()
            if not mid:
                report.add_error(sheet, row_idx, None, "Missing market_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, mid, r, dry_run=dry_run)

            if mid in existing:
                item = existing[mid]
                if item.market_name != str(r.get("market_name")):
                    item.market_name = str(r.get("market_name"))
                    item.region = str(r.get("region"))
                    item.currency = str(r.get("currency"))
                    item.market_maturity = str(r.get("market_maturity"))
                    item.regulatory_complexity = str(r.get("regulatory_complexity"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = Markets(
                    market_id=mid,
                    market_name=str(r.get("market_name")),
                    region=str(r.get("region")),
                    currency=str(r.get("currency")),
                    market_maturity=str(r.get("market_maturity")),
                    regulatory_complexity=str(r.get("regulatory_complexity")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[mid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 5. Governance_Rules
    def _ingest_governance_rules(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Governance_Rules"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {gr.rule_id: gr for gr in session.execute(select(GovernanceRules)).scalars().all()}

        for row_idx, r in records:
            rid = str(r.get("rule_id") or "").strip()
            if not rid:
                report.add_error(sheet, row_idx, None, "Missing rule_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, rid, r, dry_run=dry_run)

            if rid in existing:
                item = existing[rid]
                if item.rule_name != str(r.get("rule_name")):
                    item.rule_name = str(r.get("rule_name"))
                    item.rule_description = str(r.get("rule_description"))
                    item.priority = str(r.get("priority"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = GovernanceRules(
                    rule_id=rid,
                    rule_name=str(r.get("rule_name")),
                    rule_description=str(r.get("rule_description")),
                    priority=str(r.get("priority")),
                )
                session.add(item)
                existing[rid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 6. Business_Requests
    def _ingest_business_requests(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Business_Requests"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {br.request_id: br for br in session.execute(select(BusinessRequests)).scalars().all()}

        for row_idx, r in records:
            req_id = str(r.get("request_id") or "").strip()
            if not req_id:
                report.add_error(sheet, row_idx, None, "Missing request_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, req_id, r, dry_run=dry_run)

            dt = parse_datetime(r.get("request_date")) or datetime.now(timezone.utc)
            if req_id in existing:
                item = existing[req_id]
                if item.request_text != str(r.get("request_text")):
                    item.request_date = dt
                    item.product_context = str(r.get("product_context"))
                    item.market_context = str(r.get("market_context"))
                    item.request_text = str(r.get("request_text"))
                    item.urgency = str(r.get("urgency"))
                    item.status = str(r.get("status"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = BusinessRequests(
                    request_id=req_id,
                    request_date=dt,
                    product_context=str(r.get("product_context")),
                    market_context=str(r.get("market_context")),
                    request_text=str(r.get("request_text")),
                    urgency=str(r.get("urgency")),
                    status=str(r.get("status")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[req_id] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 7. Semantic_Models
    def _ingest_semantic_models(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Semantic_Models"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {sm.model_id: sm for sm in session.execute(select(SemanticModels)).scalars().all()}

        for row_idx, r in records:
            mid = str(r.get("model_id") or "").strip()
            if not mid:
                report.add_error(sheet, row_idx, None, "Missing model_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, mid, r, dry_run=dry_run)

            if mid in existing:
                item = existing[mid]
                if item.model_name != str(r.get("model_name")):
                    item.model_name = str(r.get("model_name"))
                    item.workspace_id = str(r.get("workspace_id"))
                    item.product_scope = str(r.get("product_scope"))
                    item.region_scope = str(r.get("region_scope"))
                    item.endorsement = str(r.get("endorsement"))
                    item.refresh_frequency = str(r.get("refresh_frequency"))
                    item.refresh_status = str(r.get("refresh_status"))
                    item.owner_id = str(r.get("owner_id"))
                    item.table_count = parse_int(r.get("table_count"))
                    item.measure_count = parse_int(r.get("measure_count"))
                    item.ai_readiness = str(r.get("ai_readiness"))
                    item.ai_issue_pattern = str(r.get("ai_issue_pattern"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = SemanticModels(
                    model_id=mid,
                    model_name=str(r.get("model_name")),
                    workspace_id=str(r.get("workspace_id")),
                    product_scope=str(r.get("product_scope")),
                    region_scope=str(r.get("region_scope")),
                    model_type=str(r.get("model_type") or "Power BI semantic model"),
                    endorsement=str(r.get("endorsement")),
                    refresh_frequency=str(r.get("refresh_frequency")),
                    refresh_status=str(r.get("refresh_status")),
                    owner_id=str(r.get("owner_id")),
                    table_count=parse_int(r.get("table_count")),
                    measure_count=parse_int(r.get("measure_count")),
                    ai_readiness=str(r.get("ai_readiness")),
                    ai_issue_pattern=str(r.get("ai_issue_pattern")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[mid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 8. KPI_Catalog
    def _ingest_kpi_catalog(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "KPI_Catalog"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {k.kpi_id: k for k in session.execute(select(KpiCatalog)).scalars().all()}

        for row_idx, r in records:
            kid = str(r.get("kpi_id") or "").strip()
            if not kid:
                report.add_error(sheet, row_idx, None, "Missing kpi_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, kid, r, dry_run=dry_run)

            if kid in existing:
                item = existing[kid]
                if item.kpi_name != str(r.get("kpi_name")):
                    item.kpi_name = str(r.get("kpi_name"))
                    item.domain = str(r.get("domain"))
                    item.unit = str(r.get("unit"))
                    item.definition_status = str(r.get("definition_status"))
                    item.approval_status = str(r.get("approval_status"))
                    item.owner_id = str(r.get("owner_id"))
                    item.description = str(r.get("description") or "")
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = KpiCatalog(
                    kpi_id=kid,
                    kpi_name=str(r.get("kpi_name")),
                    canonical_metric=parse_bool(r.get("canonical_metric"), True),
                    domain=str(r.get("domain")),
                    unit=str(r.get("unit")),
                    definition_status=str(r.get("definition_status")),
                    approval_status=str(r.get("approval_status")),
                    default_frequency=str(r.get("default_frequency")),
                    business_criticality=str(r.get("business_criticality")),
                    owner_id=str(r.get("owner_id")),
                    description=str(r.get("description") or ""),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[kid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 9. Analytics_Assets
    def _ingest_analytics_assets(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Analytics_Assets"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {a.asset_id: a for a in session.execute(select(AnalyticsAssets)).scalars().all()}

        for row_idx, r in records:
            aid = str(r.get("asset_id") or "").strip()
            if not aid:
                report.add_error(sheet, row_idx, None, "Missing asset_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, aid, r, dry_run=dry_run)

            # Preserve owner_id NULL for unowned assets (RULE-003)
            raw_owner = r.get("owner_id")
            clean_owner = str(raw_owner).strip() if (raw_owner is not None and str(raw_owner).strip() != "") else None

            created_dt = parse_datetime(r.get("created_date"))
            modified_dt = parse_datetime(r.get("last_modified"))

            if aid in existing:
                item = existing[aid]
                if item.asset_name != str(r.get("asset_name")):
                    item.asset_name = str(r.get("asset_name"))
                    item.asset_type = str(r.get("asset_type"))
                    item.platform = str(r.get("platform"))
                    item.workspace_id = str(r.get("workspace_id"))
                    item.model_id = str(r.get("model_id"))
                    item.product_scope = str(r.get("product_scope"))
                    item.market_scope = str(r.get("market_scope"))
                    item.owner_id = clean_owner
                    item.created_date = created_dt
                    item.last_modified = modified_dt
                    item.lifecycle_status = str(r.get("lifecycle_status"))
                    item.endorsement = str(r.get("endorsement"))
                    item.estimated_audience = parse_int(r.get("estimated_audience"))
                    item.classification = str(r.get("classification"))
                    item.delivery_model = str(r.get("delivery_model"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = AnalyticsAssets(
                    asset_id=aid,
                    asset_name=str(r.get("asset_name")),
                    asset_type=str(r.get("asset_type")),
                    platform=str(r.get("platform")),
                    workspace_id=str(r.get("workspace_id")),
                    model_id=str(r.get("model_id")),
                    product_scope=str(r.get("product_scope")),
                    market_scope=str(r.get("market_scope")),
                    owner_id=clean_owner,
                    created_date=created_dt,
                    last_modified=modified_dt,
                    lifecycle_status=str(r.get("lifecycle_status")),
                    endorsement=str(r.get("endorsement")),
                    estimated_audience=parse_int(r.get("estimated_audience")),
                    classification=str(r.get("classification")),
                    delivery_model=str(r.get("delivery_model")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[aid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 10. Asset_KPI_Map
    def _ingest_asset_kpi_map(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Asset_KPI_Map"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(m.asset_id, m.kpi_id): m for m in session.execute(select(AssetKpiMap)).scalars().all()}

        for row_idx, r in records:
            aid = str(r.get("asset_id") or "").strip()
            kid = str(r.get("kpi_id") or "").strip()
            key = f"{aid}_{kid}"
            if not aid or not kid:
                report.add_error(sheet, row_idx, key, "Missing asset_id or kpi_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            tuple_key = (aid, kid)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.usage_role != str(r.get("usage_role")):
                    item.usage_role = str(r.get("usage_role"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = AssetKpiMap(
                    asset_id=aid,
                    kpi_id=kid,
                    usage_role=str(r.get("usage_role")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 11. Asset_Usage
    def _ingest_asset_usage(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Asset_Usage"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(u.asset_id, u.month): u for u in session.execute(select(AssetUsage)).scalars().all()}

        for row_idx, r in records:
            aid = str(r.get("asset_id") or "").strip()
            month = str(r.get("month") or "").strip()
            key = f"{aid}_{month}"
            if not aid or not month:
                report.add_error(sheet, row_idx, key, "Missing asset_id or month")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            tuple_key = (aid, month)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.views != parse_int(r.get("views")):
                    item.views = parse_int(r.get("views"))
                    item.unique_users = parse_int(r.get("unique_users"))
                    item.exports = parse_int(r.get("exports"))
                    item.subscriptions = parse_int(r.get("subscriptions"))
                    item.avg_load_ms = parse_int(r.get("avg_load_ms"))
                    item.query_errors = parse_int(r.get("query_errors"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = AssetUsage(
                    asset_id=aid,
                    month=month,
                    views=parse_int(r.get("views")),
                    unique_users=parse_int(r.get("unique_users")),
                    exports=parse_int(r.get("exports")),
                    subscriptions=parse_int(r.get("subscriptions")),
                    avg_load_ms=parse_int(r.get("avg_load_ms")),
                    query_errors=parse_int(r.get("query_errors")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 12. Lineage_Edges
    def _ingest_lineage_edges(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Lineage_Edges"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(e.source_id, e.target_id): e for e in session.execute(select(LineageEdges)).scalars().all()}

        for row_idx, r in records:
            src = str(r.get("source_id") or "").strip()
            tgt = str(r.get("target_id") or "").strip()
            key = f"{src}_{tgt}"
            if not src or not tgt:
                report.add_error(sheet, row_idx, key, "Missing source_id or target_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            tuple_key = (src, tgt)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.relationship != str(r.get("relationship")):
                    item.edge_type = str(r.get("edge_type"))
                    item.relationship = str(r.get("relationship"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = LineageEdges(
                    source_id=src,
                    target_id=tgt,
                    edge_type=str(r.get("edge_type")),
                    relationship=str(r.get("relationship")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 13. Product_Market_Monthly
    def _ingest_product_market_monthly(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Product_Market_Monthly"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(p.product_id, p.market_id, p.month): p for p in session.execute(select(ProductMarketMonthly)).scalars().all()}

        for row_idx, r in records:
            pid = str(r.get("product_id") or "").strip()
            mid = str(r.get("market_id") or "").strip()
            month = str(r.get("month") or "").strip()
            key = f"{pid}_{mid}_{month}"
            if not pid or not mid or not month:
                report.add_error(sheet, row_idx, key, "Missing PK fields in Product_Market_Monthly")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            # CRITICAL: Preserve NULL forecast_variance_pct (110 nulls). Do NOT impute.
            var_pct = parse_float(r.get("forecast_variance_pct"))

            tuple_key = (pid, mid, month)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.net_sales_m_eur_syn != parse_float(r.get("net_sales_m_eur_syn")):
                    item.net_sales_m_eur_syn = parse_float(r.get("net_sales_m_eur_syn")) or 0.0
                    item.forecast_m_eur_syn = parse_float(r.get("forecast_m_eur_syn")) or 0.0
                    item.units_shipped_syn = parse_int(r.get("units_shipped_syn"))
                    item.forecast_variance_pct = var_pct
                    item.market_access_coverage_pct_syn = parse_float(r.get("market_access_coverage_pct_syn")) or 0.0
                    item.otif_pct_syn = parse_float(r.get("otif_pct_syn")) or 0.0
                    item.inventory_weeks_syn = parse_float(r.get("inventory_weeks_syn")) or 0.0
                    item.value_type = str(r.get("value_type") or "synthetic_commercial_measure")
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = ProductMarketMonthly(
                    product_id=pid,
                    market_id=mid,
                    month=month,
                    net_sales_m_eur_syn=parse_float(r.get("net_sales_m_eur_syn")) or 0.0,
                    forecast_m_eur_syn=parse_float(r.get("forecast_m_eur_syn")) or 0.0,
                    units_shipped_syn=parse_int(r.get("units_shipped_syn")),
                    forecast_variance_pct=var_pct,
                    market_access_coverage_pct_syn=parse_float(r.get("market_access_coverage_pct_syn")) or 0.0,
                    otif_pct_syn=parse_float(r.get("otif_pct_syn")) or 0.0,
                    inventory_weeks_syn=parse_float(r.get("inventory_weeks_syn")) or 0.0,
                    value_type=str(r.get("value_type") or "synthetic_commercial_measure"),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 14. Launch_Milestones
    def _ingest_launch_milestones(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Launch_Milestones"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {m.milestone_id: m for m in session.execute(select(LaunchMilestones)).scalars().all()}

        for row_idx, r in records:
            mid = str(r.get("milestone_id") or "").strip()
            if not mid:
                report.add_error(sheet, row_idx, None, "Missing milestone_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, mid, r, dry_run=dry_run)
            dt = parse_datetime(r.get("milestone_date")) or datetime.now(timezone.utc)

            if mid in existing:
                item = existing[mid]
                if item.status != str(r.get("status")):
                    item.status = str(r.get("status"))
                    item.milestone_date = dt
                    item.milestone_type = str(r.get("milestone_type"))
                    item.business_impact = str(r.get("business_impact"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = LaunchMilestones(
                    milestone_id=mid,
                    product_id=str(r.get("product_id")),
                    market_id=str(r.get("market_id")),
                    milestone_type=str(r.get("milestone_type")),
                    milestone_date=dt,
                    status=str(r.get("status")),
                    business_impact=str(r.get("business_impact")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[mid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 15. Market_Access
    def _ingest_market_access(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Market_Access"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(m.product_id, m.market_id): m for m in session.execute(select(MarketAccess)).scalars().all()}

        for row_idx, r in records:
            pid = str(r.get("product_id") or "").strip()
            mid = str(r.get("market_id") or "").strip()
            key = f"{pid}_{mid}"
            if not pid or not mid:
                report.add_error(sheet, row_idx, key, "Missing PK fields in Market_Access")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            tuple_key = (pid, mid)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.reimbursement_status != str(r.get("reimbursement_status")):
                    item.reimbursement_status = str(r.get("reimbursement_status"))
                    item.coverage_model = str(r.get("coverage_model"))
                    item.coverage_pct_syn = parse_float(r.get("coverage_pct_syn")) or 0.0
                    item.trend_status = str(r.get("trend_status"))
                    item.analytics_priority = str(r.get("analytics_priority"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = MarketAccess(
                    product_id=pid,
                    market_id=mid,
                    reimbursement_status=str(r.get("reimbursement_status")),
                    coverage_model=str(r.get("coverage_model")),
                    coverage_pct_syn=parse_float(r.get("coverage_pct_syn")) or 0.0,
                    trend_status=str(r.get("trend_status")),
                    analytics_priority=str(r.get("analytics_priority")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 16. Supply_Operations
    def _ingest_supply_operations(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Supply_Operations"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {(s.product_id, s.market_id): s for s in session.execute(select(SupplyOperations)).scalars().all()}

        for row_idx, r in records:
            pid = str(r.get("product_id") or "").strip()
            mid = str(r.get("market_id") or "").strip()
            key = f"{pid}_{mid}"
            if not pid or not mid:
                report.add_error(sheet, row_idx, key, "Missing PK fields in Supply_Operations")
                continue

            self._save_staging(session, import_id, sheet, row_idx, key, r, dry_run=dry_run)

            tuple_key = (pid, mid)
            if tuple_key in existing:
                item = existing[tuple_key]
                if item.supply_source != str(r.get("supply_source")):
                    item.supply_source = str(r.get("supply_source"))
                    item.primary_mode = str(r.get("primary_mode"))
                    item.otif_pct_syn = parse_float(r.get("otif_pct_syn")) or 0.0
                    item.inventory_weeks_syn = parse_float(r.get("inventory_weeks_syn")) or 0.0
                    item.forecast_accuracy_pct_syn = parse_float(r.get("forecast_accuracy_pct_syn")) or 0.0
                    item.risk_status = str(r.get("risk_status"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = SupplyOperations(
                    product_id=pid,
                    market_id=mid,
                    supply_source=str(r.get("supply_source")),
                    primary_mode=str(r.get("primary_mode")),
                    otif_pct_syn=parse_float(r.get("otif_pct_syn")) or 0.0,
                    inventory_weeks_syn=parse_float(r.get("inventory_weeks_syn")) or 0.0,
                    forecast_accuracy_pct_syn=parse_float(r.get("forecast_accuracy_pct_syn")) or 0.0,
                    risk_status=str(r.get("risk_status")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[tuple_key] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 17. Data_Quality
    def _ingest_data_quality(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Data_Quality"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {dq.issue_id: dq for dq in session.execute(select(DataQuality)).scalars().all()}

        for row_idx, r in records:
            iid = str(r.get("issue_id") or "").strip()
            if not iid:
                report.add_error(sheet, row_idx, None, "Missing issue_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, iid, r, dry_run=dry_run)

            if iid in existing:
                item = existing[iid]
                if item.issue_value != str(r.get("issue_value")):
                    item.sheet = str(r.get("sheet"))
                    item.record_id = str(r.get("record_id"))
                    item.field = str(r.get("field"))
                    item.issue_value = str(r.get("issue_value")) if r.get("issue_value") is not None else None
                    item.severity = str(r.get("severity"))
                    item.impact = str(r.get("impact"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = DataQuality(
                    issue_id=iid,
                    sheet=str(r.get("sheet")),
                    record_id=str(r.get("record_id")),
                    field=str(r.get("field")),
                    issue_value=str(r.get("issue_value")) if r.get("issue_value") is not None else None,
                    severity=str(r.get("severity")),
                    impact=str(r.get("impact")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[iid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 18. Governance_Signals
    def _ingest_governance_signals(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Governance_Signals"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {gs.signal_id: gs for gs in session.execute(select(GovernanceSignals)).scalars().all()}

        for row_idx, r in records:
            sid = str(r.get("signal_id") or "").strip()
            if not sid:
                report.add_error(sheet, row_idx, None, "Missing signal_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, sid, r, dry_run=dry_run)

            if sid in existing:
                item = existing[sid]
                if item.status != str(r.get("status")):
                    item.status = str(r.get("status"))
                    item.severity = str(r.get("severity"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = GovernanceSignals(
                    signal_id=sid,
                    asset_id=str(r.get("asset_id")),
                    signal_code=str(r.get("signal_code")),
                    severity=str(r.get("severity")),
                    status=str(r.get("status")),
                    detected_by=str(r.get("detected_by")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[sid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 19. Migration_Backlog
    def _ingest_migration_backlog(self, session: Session, ws, report: IngestionReport, import_id: str, dry_run: bool):
        sheet = "Migration_Backlog"
        report.init_sheet(sheet)
        records = self._read_sheet_records(ws)
        existing = {mb.source_asset_id: mb for mb in session.execute(select(MigrationBacklog)).scalars().all()}

        for row_idx, r in records:
            aid = str(r.get("source_asset_id") or "").strip()
            if not aid:
                report.add_error(sheet, row_idx, None, "Missing source_asset_id")
                continue

            self._save_staging(session, import_id, sheet, row_idx, aid, r, dry_run=dry_run)

            if aid in existing:
                item = existing[aid]
                if item.recommended_path_candidate != str(r.get("recommended_path_candidate")):
                    item.recommended_path_candidate = str(r.get("recommended_path_candidate"))
                    item.status = str(r.get("status"))
                    item.complexity = str(r.get("complexity"))
                    item.candidate_target_model_id = str(r.get("candidate_target_model_id"))
                    report.record_row(sheet, "updated")
                else:
                    report.record_row(sheet, "unchanged")
            else:
                item = MigrationBacklog(
                    source_asset_id=aid,
                    product_scope=str(r.get("product_scope")),
                    market_scope=str(r.get("market_scope")),
                    recommended_path_candidate=str(r.get("recommended_path_candidate")),
                    candidate_target_model_id=str(r.get("candidate_target_model_id")),
                    complexity=str(r.get("complexity")),
                    status=str(r.get("status")),
                    synthetic_reason=str(r.get("synthetic_reason")),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                session.add(item)
                existing[aid] = item
                report.record_row(sheet, "inserted")

        if not dry_run:
            session.flush()

    # 20. Documentation & Reference Sheets (Staging Preservation Only)
    def _ingest_documentation_sheets(self, session: Session, wb, report: IngestionReport, import_id: str, dry_run: bool):
        existing_keys = set(
            session.execute(
                select(StagingWorkbookRaw.record_key).where(
                    StagingWorkbookRaw.sheet_name.in_(DOCS_METADATA_SHEETS)
                )
            ).scalars().all()
        )

        for sheet_name in DOCS_METADATA_SHEETS:
            if sheet_name not in wb.sheetnames:
                continue
            report.init_sheet(sheet_name)
            ws = wb[sheet_name]
            records = self._read_sheet_records(ws)
            for row_idx, r in records:
                key = f"{sheet_name}_R{row_idx}"
                self._save_staging(session, import_id, sheet_name, row_idx, key, r, dry_run=dry_run)
                if key in existing_keys:
                    report.record_row(sheet_name, "unchanged")
                else:
                    report.record_row(sheet_name, "inserted")
                    existing_keys.add(key)

        if not dry_run:
            session.flush()


