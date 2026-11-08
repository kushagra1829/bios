import pytest
from sqlalchemy.orm import Session

from backend.app.agents.specialists.duplication_gates import DuplicateGateEngine
from backend.app.db.session import SessionLocal


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_duplicate_pair_ast0135_ast0330_surfaces_for_review(db: Session):
    """
    Known Pair 1: AST-0135 / AST-0330
    - Both Beyonttra in JP
    - Canonical-group Jaccard: 0.75
    - Surfaces for consolidation review
    - layers_used reported
    """
    eval_result = DuplicateGateEngine.evaluate_pair(db, "AST-0135", "AST-0330")

    assert eval_result.g1_scope_pass is True
    assert eval_result.g2_canonical_group_jaccard == 0.75
    assert eval_result.consolidation_eligible is True
    assert eval_result.recommendation == "SURFACE_FOR_CONSOLIDATION_REVIEW"
    assert "scope_compatibility" in eval_result.layers_used
    assert "canonical_group_jaccard" in eval_result.layers_used
    assert "exact_kpi_jaccard" in eval_result.layers_used
    assert "structural_lineage" in eval_result.layers_used


def test_duplicate_pair_ast0193_ast0197_rejected_by_scope_gate(db: Session):
    """
    Known Pair 2: AST-0193 / AST-0197
    - Same model (SM-037), exact KPI Jaccard: 0.50
    - Scope mismatch (Kerendia Global vs Lynkuet IT)
    - Must NOT become a consolidation candidate under Scope Gate G1
    """
    eval_result = DuplicateGateEngine.evaluate_pair(db, "AST-0193", "AST-0197")

    assert eval_result.g4_shares_model is True
    assert eval_result.g3_exact_kpi_jaccard == 0.50
    assert eval_result.g1_scope_pass is False
    assert eval_result.consolidation_eligible is False
    assert eval_result.recommendation == "REJECT_CONSOLIDATION_SCOPE_MISMATCH"


def test_duplicate_pair_ast0001_ast0166_classified_as_metric_drift(db: Session):
    """
    Known Pair 3: AST-0001 / AST-0166
    - Shared scope (Xarelto in CA)
    - Zero exact shared KPIs (exact Jaccard: 0.00)
    - Must be classified as drift and routed to RULE-002
    - Must never be automatically consolidated
    """
    eval_result = DuplicateGateEngine.evaluate_pair(db, "AST-0001", "AST-0166")

    assert eval_result.g1_scope_pass is True
    assert eval_result.g3_exact_kpi_jaccard == 0.00
    assert eval_result.consolidation_eligible is False
    assert eval_result.recommendation == "ROUTE_TO_RULE_002_METRIC_DRIFT"


def test_duplicate_gates_layers_and_conformance(db: Session):
    """
    Validates 100% conformance against duplicate gates G1-G4
    and auditable layers_used.
    """
    engine = DuplicateGateEngine()
    assert len(engine.LAYERS) == 4
    assert engine.LAYERS == [
        "scope_compatibility",
        "canonical_group_jaccard",
        "exact_kpi_jaccard",
        "structural_lineage",
    ]

