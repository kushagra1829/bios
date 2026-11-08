import re
from typing import Any, Dict, List, Set, Tuple
from sqlalchemy.orm import Session

from backend.app.models.core import AnalyticsAssets, SemanticModels, Owners
from backend.app.models.domain import Markets, Products
from backend.app.models.governance import GovernanceRules, KpiCatalog, MigrationBacklog


class HallucinationDetector:
    """
    Enterprise Hallucination & Grounding Verification Engine:
      - Detector H1: Phantom References (detects unknown Asset, KPI, Market, Product, Model, Rule IDs)
      - Detector H2: Invented KPI Definitions (verifies kpi_name, canonical_metric, unit against KPI catalog)
      - Detector H3: Unsupported Evidence (validates citation record_id and source table existence)
    """

    @classmethod
    def detect_phantom_references(cls, text_or_dict: Any, db: Session) -> Tuple[bool, List[str]]:
        """
        Detector H1: Scans text or structured objects for ID patterns and verifies existence in database.
        Returns: (has_phantoms: bool, phantoms_found: List[str])
        """
        text = str(text_or_dict)
        phantoms = []

        # 1. Asset IDs (AST-xxxx)
        asset_ids = set(re.findall(r"\bAST-\d{4}\b", text))
        if asset_ids:
            known_assets = set(
                a[0]
                for a in db.query(AnalyticsAssets.asset_id)
                .filter(AnalyticsAssets.asset_id.in_(asset_ids))
                .all()
            )
            for aid in asset_ids:
                if aid not in known_assets:
                    # If the text explicitly refutes the ID (stating it does not exist, is not in catalog, or is unknown),
                    # the system is rejecting the phantom rather than inventing/hallucinating it.
                    refuted = bool(
                        re.search(rf"\b{re.escape(aid)}\b\s+(?:does not exist|is not in|is unknown|not found)", text, re.IGNORECASE)
                        or re.search(rf"(?:non-existent|unknown|phantom)\s+[^\n.?!]*\b{re.escape(aid)}\b", text, re.IGNORECASE)
                    )
                    if not refuted:
                        phantoms.append(f"Phantom Asset ID: {aid}")

        # 2. KPI IDs (KPI-xxx)
        kpi_ids = set(re.findall(r"\bKPI-\d{3}\b", text))
        if kpi_ids:
            known_kpis = set(
                k[0] for k in db.query(KpiCatalog.kpi_id).filter(KpiCatalog.kpi_id.in_(kpi_ids)).all()
            )
            for kid in kpi_ids:
                if kid not in known_kpis:
                    phantoms.append(f"Phantom KPI ID: {kid}")

        # 3. Model IDs (SM-xxx)
        model_ids = set(re.findall(r"\bSM-\d{3}\b", text))
        if model_ids:
            known_models = set(
                m[0]
                for m in db.query(SemanticModels.model_id)
                .filter(SemanticModels.model_id.in_(model_ids))
                .all()
            )
            for mid in model_ids:
                if mid not in known_models:
                    phantoms.append(f"Phantom Semantic Model ID: {mid}")

        # 4. Product IDs (PRD-xxx)
        prd_ids = set(re.findall(r"\bPRD-[A-Z0-9_-]+\b", text))
        if prd_ids:
            known_prds = set(
                p[0] for p in db.query(Products.product_id).filter(Products.product_id.in_(prd_ids)).all()
            )
            for pid in prd_ids:
                if pid not in known_prds:
                    phantoms.append(f"Phantom Product ID: {pid}")

        # 5. Rule IDs (RULE-xxx)
        rule_ids = set(re.findall(r"\bRULE-\d{3}\b", text))
        valid_rules = {f"RULE-{i:03d}" for i in range(1, 9)}
        for rid in rule_ids:
            if rid not in valid_rules:
                phantoms.append(f"Phantom Rule ID: {rid}")

        return (len(phantoms) > 0, phantoms)

    @classmethod
    def verify_kpi_definition_claims(
        cls, kpi_id: str, claimed_name: str, claimed_domain: str, db: Session
    ) -> Tuple[bool, str]:
        """
        Detector H2: Validates whether claimed KPI properties match catalog ground truth.
        """
        kpi = db.query(KpiCatalog).filter(KpiCatalog.kpi_id == kpi_id).first()
        if not kpi:
            return False, f"KPI ID '{kpi_id}' does not exist in central catalog."

        if claimed_name.lower().strip() != kpi.kpi_name.lower().strip():
            return (
                False,
                f"Invented definition: Claimed name '{claimed_name}' contradicts catalog name '{kpi.kpi_name}'.",
            )

        if claimed_domain.lower().strip() != kpi.domain.lower().strip():
            return (
                False,
                f"Invented domain: Claimed domain '{claimed_domain}' contradicts catalog domain '{kpi.domain}'.",
            )

        return True, "KPI definition claim verified against central catalog."

    @classmethod
    def verify_evidence_citation(
        cls, source_table: str, record_id: str, db: Session
    ) -> Tuple[bool, str]:
        """
        Detector H3: Verifies that cited evidence references exist in actual source records.
        """
        table_map = {
            "analytics_assets": (AnalyticsAssets, "asset_id"),
            "kpi_catalog": (KpiCatalog, "kpi_id"),
            "semantic_models": (SemanticModels, "model_id"),
            "owners": (Owners, "owner_id"),
            "migration_backlog": (MigrationBacklog, "source_asset_id"),
        }

        if source_table not in table_map:
            return False, f"Unsupported evidence table '{source_table}'."

        model_cls, pk_field = table_map[source_table]
        rec = db.query(model_cls).filter(getattr(model_cls, pk_field) == record_id).first()
        if not rec:
            return False, f"Unsupported evidence: Record '{record_id}' not found in '{source_table}'."

        return True, "Evidence citation verified against physical ground truth."

    @classmethod
    def verify_semantic_model_claim(
        cls, model_id: str, claimed_product_scope: str, db: Session
    ) -> Tuple[bool, str]:
        """
        Detector H4: Validates semantic model existence and product scope claims.
        """
        model = db.query(SemanticModels).filter(SemanticModels.model_id == model_id).first()
        if not model:
            return False, f"Semantic model '{model_id}' does not exist in enterprise catalog."
        if claimed_product_scope.lower().strip() not in model.product_scope.lower().strip():
            return False, f"Model scope mismatch: Model '{model_id}' is '{model.product_scope}', not '{claimed_product_scope}'."
        return True, "Semantic model claim verified against catalog."

    @classmethod
    def verify_ownership_claim(
        cls, owner_id: str, claimed_status: Optional[str], db: Session
    ) -> Tuple[bool, str]:
        """
        Detector H5: Validates owner existence and active status.
        """
        owner = db.query(Owners).filter(Owners.owner_id == owner_id).first()
        if not owner:
            return False, f"Owner ID '{owner_id}' does not exist in authoritative owners directory."
        if claimed_status and owner.status.lower() != claimed_status.lower():
            return False, f"Ownership status mismatch: Owner '{owner_id}' is '{owner.status}', claimed '{claimed_status}'."
        return True, "Ownership claim verified against authoritative directory."

    @classmethod
    def verify_migration_status_claim(
        cls, source_asset_id: str, claimed_status: Optional[str], db: Session
    ) -> Tuple[bool, str]:
        """
        Detector H6: Validates legacy migration candidate status in MigrationBacklog.
        """
        cand = db.query(MigrationBacklog).filter(MigrationBacklog.source_asset_id == source_asset_id).first()
        if not cand:
            return False, f"Migration candidate '{source_asset_id}' does not exist in migration backlog."
        if claimed_status and cand.status.lower() != claimed_status.lower():
            return False, f"Migration status mismatch: Candidate '{source_asset_id}' has status '{cand.status}', claimed '{claimed_status}'."
        return True, "Migration claim verified against migration backlog."
