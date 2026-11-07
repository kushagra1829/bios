import pytest
from backend.app.db.session import SessionLocal
from backend.app.governance.registry import registry
from backend.app.governance.schemas import RuleId, FindingSeverity, TargetEntityType
from backend.app.governance.rules import (
    ReuseBeforeBuildRule,
    CanonicalKpiRule,
    OwnerRequiredRule,
    LineageRequiredRule,
    HighReachRequiresTrustRule,
    DoNotMigrateWasteRule,
    AiReadySemanticsRule,
    ExplainLifecycleActionRule,
)


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_rule_registry_contains_all_eight_rules():
    assert len(registry.get_all()) == 8
    for rule_id in RuleId:
        rule = registry.get(rule_id)
        assert rule is not None, f"Rule {rule_id} missing from registry"
        info = rule.get_info()
        assert info.rule_id == rule_id.value
        assert info.rule_name is not None
        assert info.rule_description is not None


def test_rule_001_reuse_before_build(db_session):
    rule = ReuseBeforeBuildRule()
    findings = rule.evaluate(db_session)
    assert len(findings) > 0

    # Check for duplicate asset title findings
    dup_asset_findings = [f for f in findings if f.target_entity_type == TargetEntityType.ASSET]
    assert len(dup_asset_findings) >= 80

    # Check for business request reuse findings
    req_findings = [f for f in findings if f.target_entity_type == TargetEntityType.REQUEST]
    assert len(req_findings) > 0

    for f in findings:
        assert f.rule_id == RuleId.RULE_001
        assert f.evidence_bundle is not None
        assert f.evidence_bundle.primary_reference is not None
        assert f.recommended_action is not None


def test_rule_002_canonical_kpi(db_session):
    rule = CanonicalKpiRule()
    findings = rule.evaluate(db_session)
    assert len(findings) > 0

    kpi_findings = [f for f in findings if f.target_entity_type == TargetEntityType.KPI]
    # Exactly 38 non-canonical KPIs in official dataset
    assert len(kpi_findings) == 38

    # Verify at least one critical finding for high/critical criticality KPIs
    critical_kpis = [f for f in kpi_findings if f.severity == FindingSeverity.CRITICAL]
    assert len(critical_kpis) > 0

    asset_kpi_findings = [f for f in findings if f.target_entity_type == TargetEntityType.ASSET]
    assert len(asset_kpi_findings) > 0


def test_rule_003_owner_required(db_session):
    rule = OwnerRequiredRule()
    findings = rule.evaluate(db_session)

    # Exactly 21 unowned assets in dataset
    unowned_critical = [
        f for f in findings
        if f.target_entity_type == TargetEntityType.ASSET and f.severity == FindingSeverity.CRITICAL
    ]
    assert len(unowned_critical) == 21

    # Exactly 65 assets with inactive owners
    inactive_owner_assets = [
        f for f in findings
        if f.target_entity_type == TargetEntityType.ASSET and f.severity == FindingSeverity.HIGH
    ]
    assert len(inactive_owner_assets) == 65

    # Semantic models with inactive owners
    inactive_models = [
        f for f in findings
        if f.target_entity_type == TargetEntityType.MODEL
    ]
    assert len(inactive_models) == 18


def test_rule_004_lineage_required(db_session):
    rule = LineageRequiredRule()
    findings = rule.evaluate(db_session)

    # Orphan model SM-009 must be flagged
    sm009_findings = [f for f in findings if f.target_entity_id == "SM-009"]
    assert len(sm009_findings) == 1
    assert sm009_findings[0].target_entity_type == TargetEntityType.MODEL

    # Downstream dependency risk findings for migration items
    downstream_risks = [f for f in findings if f.target_entity_type == TargetEntityType.ASSET]
    assert len(downstream_risks) == 15


def test_rule_005_high_reach_requires_trust(db_session):
    rule = HighReachRequiresTrustRule()
    findings = rule.evaluate(db_session)
    assert len(findings) > 0

    # Verify audience threshold enforcement
    for f in findings:
        assert f.rule_id == RuleId.RULE_005
        assert f.evidence_bundle.primary_reference.field_name is not None


def test_rule_006_do_not_migrate_waste(db_session):
    rule = DoNotMigrateWasteRule()
    findings = rule.evaluate(db_session)

    # Exactly 34 candidates in MigrationBacklog marked RETIRE or CONSOLIDATE_BEFORE_MIGRATION
    assert len(findings) == 34
    retire_findings = [f for f in findings if "RETIRE" in f.observed_value]
    assert len(retire_findings) == 22
    consolidate_findings = [f for f in findings if "CONSOLIDATE_BEFORE_MIGRATION" in f.observed_value]
    assert len(consolidate_findings) == 12


def test_rule_007_ai_readiness(db_session):
    rule = AiReadySemanticsRule()
    findings = rule.evaluate(db_session)
    assert len(findings) > 0

    # Models with AI flaws or refresh issues
    for f in findings:
        assert f.target_entity_type == TargetEntityType.MODEL
        assert f.rule_id == RuleId.RULE_007
        assert "readiness:" in f.observed_value


def test_rule_008_explain_lifecycle_action(db_session):
    rule = ExplainLifecycleActionRule()
    findings = rule.evaluate(db_session)
    assert len(findings) > 0

    # Every finding must have corroborating usage, lineage, and KPI references
    for f in findings:
        assert f.rule_id == RuleId.RULE_008
        bundle = f.evidence_bundle
        assert len(bundle.corroborating_references) >= 2
        ref_fields = {r.field_name for r in bundle.corroborating_references}
        assert "views,unique_users" in ref_fields

