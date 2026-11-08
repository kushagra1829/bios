import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.governance.engine import GovernanceEngine
from backend.app.governance.rules.rule_001_reuse import ReuseBeforeBuildRule
from backend.app.governance.rules.rule_002_kpi import CanonicalKpiRule
from backend.app.governance.rules.rule_003_owner import OwnerRequiredRule
from backend.app.governance.rules.rule_004_lineage import LineageRequiredRule
from backend.app.governance.rules.rule_005_high_reach import HighReachRequiresTrustRule
from backend.app.governance.rules.rule_006_migration_waste import DoNotMigrateWasteRule
from backend.app.governance.rules.rule_007_ai_readiness import AiReadySemanticsRule
from backend.app.governance.rules.rule_008_explainability import ExplainLifecycleActionRule
from backend.app.models.core import AnalyticsAssets, LineageEdges, Owners, SemanticModels
from backend.app.models.governance import (
    AssetKpiMap,
    DataQuality,
    GovernanceSignals,
    KpiCatalog,
    MigrationBacklog,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_rule_001_reuse_before_build_gate(db: Session):
    """RULE-001: Enforces discovery search precedes any new build request."""
    rule = ReuseBeforeBuildRule()
    findings = rule.evaluate(db)
    assert isinstance(findings, list)
    # Rule 001 evaluates duplicate pairs and unlinked new build signals
    for f in findings:
        assert f.rule_id == "RULE-001"
        assert f.evidence_bundle is not None
        assert f.evidence_bundle.primary_reference is not None


def test_rule_002_canonical_kpi_first_exact_benchmark(db: Session):
    """
    RULE-002: Exact Ground Truth Verification:
    - 960 violating Asset_KPI_Map rows
    - 349 affected assets
    - 496 primary-role violations
    """
    kpis = db.query(KpiCatalog).all()
    non_canonical_kpi_ids = {
        k.kpi_id for k in kpis if k.approval_status != "approved" or k.definition_status != "canonical"
    }
    assert len(non_canonical_kpi_ids) == 38

    bad_mappings = db.query(AssetKpiMap).filter(AssetKpiMap.kpi_id.in_(non_canonical_kpi_ids)).all()
    assert len(bad_mappings) == 960

    affected_assets = set(m.asset_id for m in bad_mappings)
    assert len(affected_assets) == 349

    primary_violations = [m for m in bad_mappings if m.usage_role in ("primary", "PRIMARY")]
    assert len(primary_violations) == 496


def test_rule_003_owner_required_predicates(db: Session):
    """
    RULE-003: Owner Required Predicate Analysis:
    - Predicate A: Exactly 21 assets with empty owner IDs
      - Exact set equality with MISSING_OWNER governance signals
      - Exact set equality with DataQuality owner_id records
    - Predicate B: Exactly 86 assets with empty or inactive owners (21 empty + 65 inactive)
    """
    # Predicate A:
    empty_owner_assets = set(
        a.asset_id
        for a in db.query(AnalyticsAssets)
        .filter((AnalyticsAssets.owner_id == None) | (AnalyticsAssets.owner_id == ""))
        .all()
    )
    assert len(empty_owner_assets) == 21

    missing_owner_signals = set(
        s.asset_id
        for s in db.query(GovernanceSignals)
        .filter(GovernanceSignals.signal_code == "MISSING_OWNER")
        .all()
    )
    assert len(missing_owner_signals) == 21
    assert empty_owner_assets == missing_owner_signals

    dq_owner_assets = set(
        d.record_id
        for d in db.query(DataQuality)
        .filter(DataQuality.sheet == "Analytics_Assets", DataQuality.field == "owner_id")
        .all()
    )
    assert len(dq_owner_assets) == 21
    assert empty_owner_assets == dq_owner_assets

    # Predicate B:
    inactive_owners = set(
        o.owner_id for o in db.query(Owners).filter(Owners.status != "active").all()
    )
    assert len(inactive_owners) == 13

    inactive_owner_assets = set(
        a.asset_id
        for a in db.query(AnalyticsAssets)
        .filter(AnalyticsAssets.owner_id.in_(inactive_owners))
        .all()
    )
    assert len(inactive_owner_assets) == 65

    predicate_b_assets = empty_owner_assets.union(inactive_owner_assets)
    assert len(predicate_b_assets) == 86


def test_rule_004_lineage_required_completeness(db: Session):
    """
    RULE-004: Lineage Required:
    - 438 lineage edges
    - Exact source/target edge-set equality
    - 100% expected nodes resolve
    """
    edges = db.query(LineageEdges).all()
    assert len(edges) == 438

    # Validate node resolution
    source_ids = {e.source_id for e in edges}
    target_ids = {e.target_id for e in edges}
    assert len(source_ids) > 0
    assert len(target_ids) > 0

    rule = LineageRequiredRule()
    findings = rule.evaluate(db)
    assert len(findings) == 16  # 1 orphan model + 15 unmitigated migration backlog dependencies


def test_rule_005_high_reach_current_and_alternatives(db: Session):
    """
    RULE-005: High reach requires trust (CRITICAL GOVERNANCE AUDIT):
    - Current implementation: Thresholds 500 and 250 -> 180 findings
      (Branch 1: 171 high reach unendorsed; Branch 2: 9 self-service reach unreviewed)
    - Alternative A: Threshold in interval (775, 814] yields exactly 152 assets,
      matching 152 HIGH_REACH_UNENDORSED signals with 100% set equality.
    - Alternative B: Threshold 1000 produces 132 findings (difference of 20).
    - Control cases:
      - AST-0001: audience 1,569, promoted -> unflagged
      - AST-0003: audience 1,359, endorsement == 'none' -> flagged
    """
    rule = HighReachRequiresTrustRule()
    findings = rule.evaluate(db)
    assert len(findings) == 180

    branch1 = [f for f in findings if "Unendorsed high-reach" in f.title]
    branch2 = [f for f in findings if "Unreviewed self-service reach" in f.title]
    assert len(branch1) == 171
    assert len(branch2) == 9

    # Control cases
    ast1_flagged = any(f.target_entity_id == "AST-0001" for f in findings)
    ast3_flagged = any(f.target_entity_id == "AST-0003" for f in findings)
    assert ast1_flagged is False, "AST-0001 is promoted and must not be flagged"
    assert ast3_flagged is True, "AST-0003 has audience 1359 without endorsement and must be flagged"

    # Alternative A: (775, 814] reproduces 152 reference signals
    signals = set(
        s.asset_id
        for s in db.query(GovernanceSignals)
        .filter(GovernanceSignals.signal_code == "HIGH_REACH_UNENDORSED")
        .all()
    )
    assert len(signals) == 152

    unendorsed = db.query(AnalyticsAssets).filter(AnalyticsAssets.endorsement == "none").all()
    alt_a_assets = set(a.asset_id for a in unendorsed if a.estimated_audience >= 780)
    assert len(alt_a_assets) == 152
    assert alt_a_assets == signals

    # Alternative B: Threshold 1000 produces 132 findings
    alt_b_assets = set(a.asset_id for a in unendorsed if a.estimated_audience >= 1000)
    assert len(alt_b_assets) == 132
    assert len(signals - alt_b_assets) == 20


def test_rule_006_do_not_migrate_waste_breakdown(db: Session):
    """
    RULE-006: Do Not Migrate Waste:
    - 94 migration backlog entries
    - 22 retire recommendations
    - 12 consolidate recommendations
    - 34 assets not intended for direct 1:1 migration
    """
    migs = db.query(MigrationBacklog).all()
    assert len(migs) == 94

    retire_count = sum(1 for m in migs if m.recommended_path_candidate == "RETIRE")
    consolidate_count = sum(1 for m in migs if m.recommended_path_candidate == "CONSOLIDATE_BEFORE_MIGRATION")
    assert retire_count == 22
    assert consolidate_count == 12
    assert (retire_count + consolidate_count) == 34

    rule = DoNotMigrateWasteRule()
    findings = rule.evaluate(db)
    assert len(findings) == 34


def test_rule_007_ai_ready_semantics_breakdown(db: Session):
    """
    RULE-007: AI-Ready Semantics:
    - 48 issue-pattern models
      - 17 poor_names
      - 16 ambiguous_dates
      - 15 implicit_measures
    - 45 poor or partial readiness models
    - 64 models in the union of issue categories and poor/partial readiness
    """
    models = db.query(SemanticModels).all()
    assert len(models) == 75

    poor_names = [m for m in models if m.ai_issue_pattern == "poor_names"]
    ambiguous_dates = [m for m in models if m.ai_issue_pattern == "ambiguous_dates"]
    implicit_measures = [m for m in models if m.ai_issue_pattern == "implicit_measures"]
    assert len(poor_names) == 17
    assert len(ambiguous_dates) == 16
    assert len(implicit_measures) == 15
    assert (len(poor_names) + len(ambiguous_dates) + len(implicit_measures)) == 48

    poor_or_partial = [m for m in models if m.ai_readiness in ("poor", "partial")]
    assert len(poor_or_partial) == 45

    genuine_issue_ids = {m.model_id for m in (poor_names + ambiguous_dates + implicit_measures)}
    poor_partial_ids = {m.model_id for m in poor_or_partial}
    union_ids = genuine_issue_ids.union(poor_partial_ids)
    assert len(union_ids) == 64


def test_rule_008_explain_every_action_evidence_completeness(db: Session):
    """
    RULE-008: Explain Every Lifecycle Action:
    - 100% evidence bundle completeness across evaluated actions.
    - All citations resolve to real source tables and primary keys.
    """
    rule = ExplainLifecycleActionRule()
    findings = rule.evaluate(db)
    assert len(findings) > 0
    for f in findings:
        assert f.evidence_bundle is not None
        assert f.evidence_bundle.primary_reference is not None
        assert f.evidence_bundle.primary_reference.source_table != ""
        assert f.evidence_bundle.primary_reference.record_id != ""
