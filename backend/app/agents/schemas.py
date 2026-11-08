from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class DecisionType(str, Enum):
    REUSE = "REUSE"
    CONSOLIDATE = "CONSOLIDATE"
    MODIFY = "MODIFY"
    MIGRATE = "MIGRATE"
    RETIRE = "RETIRE"
    BUILD_NEW = "BUILD_NEW"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    # The request asked a question (data, governance or migration) rather than for an asset.
    # The answer is in AssistantWorkflowResponse.answer; no lifecycle action is proposed.
    INFORMATIONAL = "INFORMATIONAL"


class RequestType(str, Enum):
    """What the user actually asked for. A request can carry several."""
    BUSINESS_DATA_QUESTION = "BUSINESS_DATA_QUESTION"
    DATA_QUESTION = "BUSINESS_DATA_QUESTION"
    ASSET_REQUEST = "ASSET_REQUEST"
    GOVERNANCE_QUESTION = "GOVERNANCE_QUESTION"
    MIGRATION_QUESTION = "MIGRATION_QUESTION"


class ActionStatus(str, Enum):
    """Whether the recommended action can proceed. Set deterministically by the Decision Agent."""
    ACTIONABLE = "ACTIONABLE"  # Can proceed without a consequential approval (e.g. reuse access).
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"  # Can proceed only after an authorised human approves.
    BLOCKED = "BLOCKED"  # A governance blocker on the target prevents the action.
    NEEDS_INPUT = "NEEDS_INPUT"  # The user must clarify first.
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Informational answer, no action proposed.


class MatchTier(str, Enum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"


class ExecutionMode(str, Enum):
    """How an agent step actually produced its output. Recorded on every trace."""
    LLM_ASSISTED = "LLM_ASSISTED"  # A real LLM call succeeded and passed validation.
    DETERMINISTIC = "DETERMINISTIC"  # No LLM attempted: by design or by configuration.
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"  # LLM wanted but unavailable, failed or rejected.


class LLMCallMetadata(BaseModel):
    """Measured facts about one adapter call, including all of its bounded retries."""
    provider: str
    model: str
    schema_name: Optional[str] = None
    status: str = Field(description="success, invalid_output, timeout, unavailable or rejected_by_guardrail")
    attempts: int = 1
    duration_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    model_load_ms: Optional[float] = None
    processor: str = Field(default="unknown", description="gpu, cpu, mixed or unknown, as reported by the provider")
    size_vram_bytes: Optional[int] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


class AgentExecutionMetadata(BaseModel):
    """Provider, model and execution mode for one agent step."""
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_reason: Optional[str] = None
    llm_calls: List[LLMCallMetadata] = Field(default_factory=list)


# LLM output contracts. These are proposals: agents validate them against the raw
# prompt, the catalog or the authoritative decision before using any of their content.
# Fields have no defaults on purpose: a default drops the field from the JSON schema's
# "required" list, and Ollama's schema-constrained output then lets the model omit it.
class KpiMapping(BaseModel):
    requested_phrase: str
    catalog_kpi_name: str


class IntentExtraction(BaseModel):
    products: List[str]
    markets: List[str]
    kpi_mappings: List[KpiMapping]
    unmapped_metrics: List[str]
    dimensions: List[str]
    time_periods: List[str]
    business_purpose: str


class KpiEquivalenceAssessment(str, Enum):
    EQUIVALENT = "equivalent"
    RELATED_NOT_EQUIVALENT = "related_not_equivalent"
    UNCERTAIN = "uncertain"


class KpiEquivalenceReview(BaseModel):
    requested_metric: str
    matched_kpi_id: str
    assessment: KpiEquivalenceAssessment
    note: str


class KpiReviewOutput(BaseModel):
    reviews: List[KpiEquivalenceReview]


class DecisionNarrative(BaseModel):
    decision_echo: DecisionType
    human_approval_required_echo: bool
    blocker_count_echo: int
    summary: str = Field(min_length=1)


class IntentFields(BaseModel):
    """The interpretation fields of an intent, used to store the deterministic baseline."""
    products: List[str] = Field(default_factory=list)
    markets: List[str] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    time_periods: List[str] = Field(default_factory=list)
    business_purpose: str = ""
    missing_or_ambiguous: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class EnrichmentStatus(str, Enum):
    ACCEPTED = "accepted"  # Validated, and added to the normalized intent.
    CONFIRMED_BASELINE = "confirmed_baseline"  # The parser had already found it.
    REJECTED = "rejected"  # Failed validation, and not used.


class EnrichmentDecision(BaseModel):
    category: str
    proposed: str
    normalized: Optional[str] = None
    status: EnrichmentStatus
    reason: str


class IntentResolution(BaseModel):
    """How the normalized intent was reached, kept separately from the intent's own fields."""
    original_request: str
    deterministic_intent: IntentFields
    llm_proposal: Optional[IntentExtraction] = None
    accepted: List[EnrichmentDecision] = Field(default_factory=list)
    confirmed: List[EnrichmentDecision] = Field(default_factory=list)
    rejected: List[EnrichmentDecision] = Field(default_factory=list)


class EntityAmbiguity(BaseModel):
    """A term that could mean a catalog entity but wasn't resolved to one."""
    category: str
    term: str
    candidates: List[str] = Field(default_factory=list)
    reason: str


class GeographyStatus(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_SPECIFIED = "NOT_SPECIFIED"


class GeographicPhrase(BaseModel):
    """One piece of geography as the user wrote it, and what it was resolved to."""
    original_phrase: str
    normalized_scope: str
    resolved_market_ids: List[str] = Field(default_factory=list)
    suggested_market_ids: List[str] = Field(
        default_factory=list,
        description="Unverified suggestions that need the user's confirmation. They are never used as matches.",
    )
    catalog_evidence: List[str] = Field(default_factory=list, description="Facts recorded in the catalog")
    external_context: List[str] = Field(default_factory=list, description="General knowledge the catalog doesn't record")
    status: GeographyStatus
    explanation: str


class GeographyResolution(BaseModel):
    """How the request's geography was resolved. The resolved values also appear in BusinessIntent.markets."""
    status: GeographyStatus = GeographyStatus.NOT_SPECIFIED
    phrases: List[GeographicPhrase] = Field(default_factory=list)
    resolved_market_ids: List[str] = Field(default_factory=list, description="Catalog market IDs, plus asset scopes such as Global")
    unresolved_geography: List[str] = Field(default_factory=list, description="Phrases not fully resolved")
    explanation: str = ""


class BusinessIntent(BaseModel):
    # Frozen so every agent is guaranteed to receive the same normalized intent.
    model_config = ConfigDict(frozen=True)

    raw_prompt: str
    products: List[str] = Field(default_factory=list, description="Extracted pharma products (e.g. Nubeqa, Xarelto, Beyonttra, Kerendia)")
    markets: List[str] = Field(default_factory=list, description="Extracted markets/regions (e.g. Global, US, EMEA, JP, DE)")
    kpis: List[str] = Field(default_factory=list, description="Extracted business KPIs (e.g. revenue growth, forecast variance, market access)")
    dimensions: List[str] = Field(default_factory=list, description="Extracted slicing dimensions (e.g. by country, by month, by channel)")
    time_periods: List[str] = Field(default_factory=list, description="Extracted time horizons (e.g. monthly, YTD, Q3)")
    business_purpose: str = Field(description="Summary of the analytical goal")
    missing_or_ambiguous: List[str] = Field(default_factory=list, description="Requirements identified as missing or underspecified")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    ambiguities: List[EntityAmbiguity] = Field(default_factory=list, description="Terms left unresolved because they could mean several things")
    interpretation_notes: List[str] = Field(default_factory=list, description="Aliases, regions and close spellings the parser resolved")
    unresolved_terms: List[str] = Field(default_factory=list, description="Metrics the request states that have no catalog KPI, as proposed by the LLM")
    resolution: Optional[IntentResolution] = Field(default=None, description="Audit record of the baseline, LLM proposal and each validation outcome")
    geography: Optional[GeographyResolution] = Field(default=None, description="Requested geography kept separately from the markets it resolved to")
    request_types: List[RequestType] = Field(
        default_factory=list,
        description="Every request type detected, primary first. Set by the deterministic request router.",
    )
    request_type_evidence: List[str] = Field(default_factory=list, description="The phrases that decided request_types")
    asset_ids_mentioned: List[str] = Field(default_factory=list, description="AST-/SM- identifiers stated in the request")
    duplication_question: bool = Field(default=False, description="The request asks about existing similar or duplicate assets")
    title_topics: List[str] = Field(default_factory=list, description="Asset-title topics stated in the request, e.g. 'Budget Mgmt'")

    @property
    def primary_request_type(self) -> RequestType:
        return self.request_types[0] if self.request_types else RequestType.ASSET_REQUEST


class DiscoveredAsset(BaseModel):
    asset_id: str
    asset_name: str
    match_tier: MatchTier
    product_scope: str
    market_scope: str
    platform: str
    endorsement: str
    lifecycle_status: str
    match_score: float = Field(ge=0.0, le=1.0)
    match_reasons: List[str] = Field(default_factory=list)
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    model_endorsement: Optional[str] = None
    owner_name: Optional[str] = None
    estimated_audience: int = 0
    evidence: Dict[str, Any] = Field(default_factory=dict)


class DiscoveryResult(BaseModel):
    exact_matches: List[DiscoveredAsset] = Field(default_factory=list)
    partial_matches: List[DiscoveredAsset] = Field(default_factory=list)
    weak_candidates: List[DiscoveredAsset] = Field(default_factory=list)
    total_searched: int = 0
    search_notes: str = ""
    # Evidence retrieved for question-type requests. Computed deterministically from source records.
    data_answer: Optional["DataAnswer"] = None
    governance_answer: Optional["GovernanceAnswer"] = None
    migration_answer: Optional["MigrationAnswer"] = None
    title_topic_matches: List[str] = Field(default_factory=list, description="Asset IDs whose title carries a requested topic")


class KpiMatch(BaseModel):
    requested_metric: str
    matched_kpi_id: Optional[str] = None
    matched_kpi_name: Optional[str] = None
    domain: Optional[str] = None
    approval_status: Optional[str] = None
    definition_status: Optional[str] = None
    is_canonical: bool = False
    is_approved: bool = False
    semantic_equivalence_notes: str = ""
    conflicts: List[str] = Field(default_factory=list)
    alternative_kpis: List[Dict[str, str]] = Field(default_factory=list)


class KpiAnalysisResult(BaseModel):
    matches: List[KpiMatch] = Field(default_factory=list)
    canonical_approved_kpi_ids: List[str] = Field(default_factory=list)
    unapproved_or_conflicted_kpi_ids: List[str] = Field(default_factory=list)
    unmatched_requested_metrics: List[str] = Field(default_factory=list)
    has_conflicts: bool = False
    summary: str = ""
    llm_review: List[KpiEquivalenceReview] = Field(
        default_factory=list,
        description="Advisory only: never changes KPI IDs, approval status or conflict flags.",
    )


class DuplicateCandidate(BaseModel):
    asset_id: str
    asset_name: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    structural_similarity: float = Field(ge=0.0, le=1.0, description="Shared semantic model, tables, workspace")
    kpi_similarity: float = Field(ge=0.0, le=1.0, description="Shared mapped KPIs and measures")
    semantic_similarity: float = Field(ge=0.0, le=1.0, description="Title and context similarity")
    endorsement: str
    lifecycle_status: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class DuplicationResult(BaseModel):
    has_duplicates: bool = False
    candidates: List[DuplicateCandidate] = Field(default_factory=list)
    highest_similarity_score: float = 0.0
    primary_duplicate_asset_id: Optional[str] = None
    explanation: str = ""
    gate_evaluations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Staged G1-G4 pair evaluations among existing in-scope assets (estate duplicates)",
    )
    consolidation_eligible_pairs: List[List[str]] = Field(default_factory=list)
    title_alike_groups: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Assets that share a title but were evaluated by the gates; title similarity alone never justifies consolidation",
    )


class GovernanceAgentResult(BaseModel):
    # Forbid unknown fields: a misspelt keyword once left active_finding_ids silently empty.
    model_config = ConfigDict(extra="forbid")

    blockers: List[str] = Field(default_factory=list, description="Strict blockers preventing action")
    warnings: List[str] = Field(default_factory=list, description="Governance warnings or risks")
    applicable_rule_ids: List[str] = Field(default_factory=list)
    active_finding_ids: List[str] = Field(default_factory=list, description="All active findings on the candidate assets")
    human_approval_required: bool = True
    evidence_references: List[Dict[str, Any]] = Field(default_factory=list)
    request_finding_ids: List[str] = Field(default_factory=list, description="Findings on assets in the requested scope or recommended as a target")
    out_of_scope_finding_ids: List[str] = Field(default_factory=list, description="Findings on other candidate assets. These never block the request.")
    out_of_scope_warnings: List[str] = Field(default_factory=list, description="Critical and high findings outside the requested scope, for awareness")


class DecisionAlternative(BaseModel):
    action: str
    target_id: Optional[str] = None
    pros: str
    cons: str


class DecisionResult(BaseModel):
    decision: DecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    primary_recommendation: str
    rationale: str
    target_asset_ids: List[str] = Field(default_factory=list)
    target_model_ids: List[str] = Field(default_factory=list)
    alternatives: List[DecisionAlternative] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    human_approval_required: bool = True
    next_steps: List[str] = Field(default_factory=list)
    active_finding_ids: List[str] = Field(
        default_factory=list,
        description="Active governance findings on the candidate assets, from the Governance Agent.",
    )
    out_of_scope_warnings: List[str] = Field(
        default_factory=list,
        description="Governance warnings about assets outside the requested scope. Blockers and warnings above are request-specific.",
    )
    llm_narrative: Optional[str] = Field(
        default=None,
        description="Advisory plain-language summary. Every other field is computed deterministically.",
    )
    action_status: ActionStatus = Field(
        default=ActionStatus.REQUIRES_APPROVAL,
        description="Whether the recommended action can proceed, after governance blockers on the target are applied.",
    )
    ineligible_targets: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate targets rejected because a governance control forbids acting on them, with the reason.",
    )
    validation_notes: List[str] = Field(
        default_factory=list,
        description="Outcome of the mandatory deterministic post-decision validation (answering/final_validation.py).",
    )


# ---------------------------------------------------------------------------
# Structured answers (Final AI Intelligence Transformation). Every value here is computed
# deterministically from source records; nothing is produced by an LLM.
# ---------------------------------------------------------------------------
class DataFigure(BaseModel):
    label: str
    value: Optional[float] = None
    unit: str = ""
    detail: str = ""


class DataCoverage(BaseModel):
    records_used: int = 0
    records_expected: int = 0
    months_covered: List[str] = Field(default_factory=list)
    months_missing_in_requested_range: List[str] = Field(default_factory=list)
    null_values_excluded: int = 0
    value_type_counts: Dict[str, int] = Field(default_factory=dict)
    dataset_period: str = ""


class DataAnswer(BaseModel):
    status: str = Field(description="ANSWERED, PARTIAL, NO_DATA, NEEDS_CLARIFICATION or UNSUPPORTED")
    operation: str = Field(description="TOTAL, AVERAGE, TREND, COMPARE, RANK, FORECAST_VS_ACTUAL, CHANGE or NONE")
    measure_field: Optional[str] = None
    measure_label: str = ""
    unit: str = ""
    aggregation: str = ""
    products: List[str] = Field(default_factory=list)
    markets: List[str] = Field(default_factory=list)
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    headline: str = ""
    figures: List[DataFigure] = Field(default_factory=list)
    series: List[Dict[str, Any]] = Field(default_factory=list)
    comparison: str = ""
    coverage: DataCoverage = Field(default_factory=DataCoverage)
    source: Dict[str, Any] = Field(default_factory=dict)
    caveats: List[str] = Field(default_factory=list)
    clarification: List[str] = Field(default_factory=list)


class FindingView(BaseModel):
    """One governance finding as shown to a business user. Deduplicated by (rule, asset, control)."""
    rule_id: str
    severity: str
    asset_id: Optional[str] = None
    kind: str = Field(description="BLOCKER, WARNING or DIRECTIVE")
    effect: str = Field(description="PREVENTS_ACTION, REQUIRES_REVIEW or INFORMATIONAL")
    message: str
    required_action: str = ""
    finding_ids: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list, description="Backend strings merged into this entry")
    affects_target: bool = False


class GovernanceAnswer(BaseModel):
    status: str = Field(description="ANSWERED, NO_MATCH, NOT_FOUND or NEEDS_CLARIFICATION")
    question_kind: str
    headline: str = ""
    explanation: List[str] = Field(default_factory=list)
    rules: List[Dict[str, str]] = Field(default_factory=list)
    assets: List[Dict[str, Any]] = Field(default_factory=list)
    total_matching: int = 0
    findings: List[FindingView] = Field(default_factory=list)
    kpis: List[Dict[str, Any]] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    source: Dict[str, Any] = Field(default_factory=dict)


class MigrationAnswer(BaseModel):
    status: str = Field(description="ANSWERED, NO_MATCH or NEEDS_CLARIFICATION")
    headline: str = ""
    groups: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    total_matching: int = 0
    explanation: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    approval_note: str = ""
    source: Dict[str, Any] = Field(default_factory=dict)


class GovernancePresentation(BaseModel):
    blockers: List[FindingView] = Field(default_factory=list)
    warnings: List[FindingView] = Field(default_factory=list)
    directives: List[FindingView] = Field(default_factory=list)
    backend_blocker_count: int = 0
    backend_warning_count: int = 0
    displayed_blocker_count: int = 0
    displayed_warning_count: int = 0
    displayed_directive_count: int = 0
    out_of_scope_count: int = 0


class AssistantPresentation(BaseModel):
    """The business-facing answer. Governance is always rendered last."""
    response_type: str = Field(description="DATA_ANSWER, ASSET_RECOMMENDATION, GOVERNANCE_ANSWER, MIGRATION_RECOMMENDATION or CLARIFICATION")
    recommended_action: str
    action_label: str
    action_status: str
    direct_answer: str
    why: List[str] = Field(default_factory=list)
    matching_assets: List[Dict[str, Any]] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    human_approval_required: bool = False
    approval_explanation: str = ""
    confidence_explanation: str = ""
    governance: GovernancePresentation = Field(default_factory=GovernancePresentation)


# API Schema Models
class AssistantRequestCreate(BaseModel):
    prompt: str = Field(min_length=3, description="Natural-language business analytics request")


class AssistantRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    raw_prompt: str
    status: str
    created_at: datetime
    updated_at: datetime


class AgentTraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    request_id: str
    agent_name: str
    step_order: int
    status: str
    duration_ms: float
    input_json: Optional[str] = None
    output_json: Optional[str] = None
    error_message: Optional[str] = None
    execution_metadata_json: Optional[str] = None
    executed_at: datetime


class AssistantRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: str
    request_id: str
    decision: str
    confidence: float
    primary_recommendation: str
    rationale: str
    alternatives_json: Optional[str] = None
    blockers_json: Optional[str] = None
    warnings_json: Optional[str] = None
    matched_assets_json: Optional[str] = None
    kpi_analysis_json: Optional[str] = None
    duplicate_analysis_json: Optional[str] = None
    approval_required: bool
    created_at: datetime


class AssistantWorkflowResponse(BaseModel):
    request_id: str
    raw_prompt: str
    status: str
    intent: BusinessIntent
    recommendation: DecisionResult
    discovery: DiscoveryResult
    kpi_analysis: KpiAnalysisResult
    duplication: DuplicationResult
    governance: GovernanceAgentResult
    traces: List[AgentTraceOut]
    request_types: List[RequestType] = Field(default_factory=list)
    data_answer: Optional[DataAnswer] = None
    governance_answer: Optional[GovernanceAnswer] = None
    migration_answer: Optional[MigrationAnswer] = None
    presentation: Optional[AssistantPresentation] = None



DiscoveryResult.model_rebuild()
