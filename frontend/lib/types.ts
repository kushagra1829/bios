export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  timestamp: string;
  ai_provider?: string;
  ollama_status?: string;
}

export interface GovernanceRule {
  rule_id: string;
  rule_name: string;
  category: string;
  description: string;
  severity: "critical" | "high" | "medium" | "low";
  active: boolean;
  business_impact?: string;
  remediation_guidance?: string;
}

export interface EvidenceReference {
  source_table: string;
  record_id: string;
  field_name?: string;
  observed_value?: string;
  expected_value?: string;
}

export interface EvidenceBundle {
  primary_reference: EvidenceReference;
  supporting_references?: EvidenceReference[];
  data_quality_record_id?: string;
  lineage_edge_id?: string;
  rule_citation?: string;
  explanation_narrative?: string;
}

export interface GovernanceFinding {
  finding_id: string;
  rule_id: string;
  target_entity_type: string;
  target_entity_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "open" | "resolved" | "suppressed";
  explanation?: string;
  evidence_bundle?: EvidenceBundle;
  created_at: string;
  updated_at?: string;
}

export interface GovernanceSummary {
  total_active_findings: number;
  findings_by_severity: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  findings_by_rule: Record<string, number>;
  rules_evaluated_count: number;
}

export interface AnalyticsAsset {
  asset_id: string;
  asset_name: string;
  asset_type: string;
  platform: "Tableau" | "Power BI";
  workspace_id?: string;
  model_id?: string;
  product_scope?: string;
  market_scope?: string;
  owner_id?: string;
  owner_name?: string;
  lifecycle_status: string;
  endorsement: "certified" | "promoted" | "none";
  estimated_audience?: number;
  classification?: string;
  created_date?: string;
  last_modified?: string;
  findings_count?: number;
  delivery_model?: string;
}

export interface SemanticModel {
  model_id: string;
  model_name: string;
  platform: string;
  workspace_id?: string;
  ai_readiness?: string;
  ai_issue_pattern?: string;
  endorsement?: string;
  table_count?: number;
  measure_count?: number;
}

export interface CanonicalKpi {
  kpi_id: string;
  kpi_name: string;
  definition_status: "canonical" | "non_canonical";
  approval_status: "approved" | "pending" | "rejected";
  domain?: string;
  calculation_formula?: string;
}

export interface AgentTrace {
  trace_id: string;
  request_id?: string;
  step_order: number;
  agent_name: string;
  status?: string;
  duration_ms?: number;
  latency_ms?: number;
  provider?: string;
  model?: string;
  execution_mode?: string;
  input_json?: string;
  output_json?: string;
  input_summary?: Record<string, any>;
  output_summary?: Record<string, any>;
  execution_metadata_json?: string;
  error_message?: string;
  executed_at?: string;
  created_at?: string;
}

export interface DiscoveredAssetCandidate {
  asset_id: string;
  asset_name: string;
  match_tier: string;
  product_scope?: string;
  market_scope?: string;
  platform: string;
  endorsement: string;
  lifecycle_status: string;
  match_score?: number;
  match_reasons?: string[];
  model_id?: string;
}

export interface DuplicateCandidate {
  asset_id: string;
  asset_name: string;
  similarity_score?: number;
  structural_similarity?: number;
  kpi_similarity?: number;
  semantic_similarity?: number;
  endorsement?: string;
  lifecycle_status?: string;
}

export interface AssistantRecommendation {
  decision: "REUSE" | "CONSOLIDATE" | "MODIFY" | "RETIRE" | "MIGRATE" | "BUILD_NEW" | "NEEDS_CLARIFICATION" | "INFORMATIONAL";
  action_status?: "ACTIONABLE" | "REQUIRES_APPROVAL" | "BLOCKED" | "NEEDS_INPUT" | "NOT_APPLICABLE";
  ineligible_targets?: { asset_id: string; reasons: string[] }[];
  confidence?: number;
  primary_recommendation: string;
  rationale: string;
  target_asset_ids: string[];
  target_model_ids: string[];
  alternatives?: any[];
  blockers?: string[];
  warnings?: string[];
  human_approval_required: boolean;
  next_steps?: string[];
}

export interface AssistantWorkflowResponse {
  request_id: string;
  raw_prompt: string;
  status: string;
  intent?: {
    products?: string[];
    markets?: string[];
    kpis?: string[];
    dimensions?: string[];
    business_purpose?: string;
    confidence?: number;
  };
  recommendation?: AssistantRecommendation;
  discovery?: {
    exact_matches?: DiscoveredAssetCandidate[];
    partial_matches?: DiscoveredAssetCandidate[];
    weak_candidates?: DiscoveredAssetCandidate[];
    total_searched?: number;
  };
  duplication?: {
    has_duplicates?: boolean;
    highest_similarity_score?: number;
    primary_duplicate_asset_id?: string;
    candidates?: DuplicateCandidate[];
  };
  governance?: {
    active_finding_ids?: string[];
    has_unowned_candidate?: boolean;
    has_unendorsed_high_reach?: boolean;
    has_non_canonical_kpis?: boolean;
    has_lineage_blocker?: boolean;
  };
  traces?: AgentTrace[];
  request_types?: RequestType[];
  data_answer?: DataAnswer | null;
  governance_answer?: { status: string; question_kind: string; headline: string; total_matching: number; assets: Record<string, any>[]; kpis: Record<string, any>[] } | null;
  migration_answer?: { status: string; headline: string; total_matching: number; groups: Record<string, Record<string, any>[]> } | null;
  presentation?: AssistantPresentation | null;
}

export type RequestType = "DATA_QUESTION" | "BUSINESS_DATA_QUESTION" | "ASSET_REQUEST" | "GOVERNANCE_QUESTION" | "MIGRATION_QUESTION";

export interface DataFigure {
  label: string;
  value: number | null;
  unit: string;
  detail?: string;
}

export interface DataAnswer {
  status: "ANSWERED" | "PARTIAL" | "NO_DATA" | "NEEDS_CLARIFICATION" | "UNSUPPORTED";
  operation: string;
  measure_label: string;
  unit: string;
  aggregation: string;
  headline: string;
  figures: DataFigure[];
  series: Record<string, any>[];
  comparison: string;
  coverage: { records_used: number; records_expected: number; months_missing_in_requested_range: string[]; value_type_counts: Record<string, number>; dataset_period: string };
  source: Record<string, any>;
  caveats: string[];
  clarification: string[];
}

export interface FindingView {
  rule_id: string;
  severity: string;
  asset_id?: string | null;
  kind: "BLOCKER" | "WARNING" | "DIRECTIVE";
  effect: "PREVENTS_ACTION" | "REQUIRES_REVIEW" | "INFORMATIONAL";
  message: string;
  required_action?: string;
  finding_ids?: string[];
  sources?: string[];
  affects_target?: boolean;
}

export interface AssistantPresentation {
  response_type: "DATA_ANSWER" | "ASSET_RECOMMENDATION" | "GOVERNANCE_ANSWER" | "MIGRATION_RECOMMENDATION" | "CLARIFICATION";
  recommended_action: string;
  action_label: string;
  action_status: string;
  direct_answer: string;
  why: string[];
  matching_assets: Record<string, any>[];
  next_steps: string[];
  human_approval_required: boolean;
  approval_explanation: string;
  confidence_explanation: string;
  governance: {
    blockers: FindingView[];
    warnings: FindingView[];
    directives: FindingView[];
    backend_blocker_count: number;
    backend_warning_count: number;
    displayed_blocker_count: number;
    displayed_warning_count: number;
    displayed_directive_count: number;
    out_of_scope_count: number;
  };
}

export interface ApprovalRequest {
  approval_id: string;
  target_entity_type: string;
  target_entity_id: string;
  action_type: string;
  recommendation_ref?: string;
  requester_id: string;
  requester_role: string;
  required_role: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED" | "EXPIRED";
  title: string;
  description: string;
  evidence_snapshot_json?: string;
  blockers_json?: string;
  warnings_json?: string;
  decided_by_id?: string;
  decided_by_role?: string;
  decision_reason?: string;
  decided_at?: string;
  created_at: string;
  updated_at?: string;
  expires_at?: string;
}

export interface ApprovalQueueSummary {
  total_pending: number;
  total_approved: number;
  total_rejected: number;
  total_changes_requested: number;
  total_expired?: number;
  expired_count?: number;
  pending_by_role?: Record<string, number>;
  pending_by_action?: Record<string, number>;
}

export interface ApprovalTransition {
  transition_id: string;
  approval_id: string;
  from_state: string;
  to_state: string;
  actor_id: string;
  actor_role: string;
  comment?: string;
  transitioned_at: string;
}

export interface MigrationCandidate {
  migration_id: string;
  run_id: string;
  source_asset_id: string;
  source_asset_name?: string;
  recommended_action: string;
  business_value: string;
  technical_complexity: "low" | "medium" | "high";
  candidate_target_model_id?: string;
  semantic_model_readiness?: string;
  kpi_compatibility_score: number;
  downstream_dependency_count: number;
  rationalization_rationale: string;
  blockers?: string[];
  warnings?: string[];
  approval_required: boolean;
  assessed_at: string;
}

export interface MigrationSummary {
  total_tableau_assets: number;
  total_candidates?: number;
  actions_breakdown: Record<string, number>;
  complexity_breakdown: Record<string, number>;
  direct_migrate_count: number;
  consolidate_count: number;
  retire_instead_count: number;
  retire_count?: number;
  fix_before_migrate_count: number;
  hold_review_count: number;
  estimated_effort_reduction_pct: number;
  candidate_target_models: string[];
}

export interface DashboardSpecification {
  spec_id: string;
  title: string;
  business_purpose: string;
  request_id?: string;
  approval_id?: string;
  product_scope?: string;
  market_scope?: string;
  semantic_model_id?: string;
  kpi_ids: string[];
}

export interface GeneratedArtifact {
  artifact_id: string;
  spec_id: string;
  artifact_name: string;
  format?: string;
  output_directory: string;
  root_pbip_file: string;
  provenance_json?: string;
  validation_status: string;
  created_at: string;
}

export interface AuditEvent {
  event_id: string;
  actor_id: string;
  actor_role: string;
  event_type: string;
  target_entity_type: string;
  target_entity_id: string;
  action: string;
  before_state_json?: string;
  after_state_json?: string;
  reason?: string;
  created_at: string;
}

export interface IntegrationStatus {
  connector_id: string;
  connector_name: string;
  platform: string;
  status: "NOT_CONFIGURED" | "CONNECTED" | "AUTH_FAILED" | "PERMISSION_DENIED" | "SYNC_FAILED";
  auth_type: string;
  last_tested_at?: string;
  last_synced_at?: string;
  error_message?: string;
  discovered_workspaces: number;
  discovered_reports: number;
  discovered_models: number;
  required_env_vars: string[];
  configured_env_vars: string[];
}

export interface ConnectionTestResult {
  status: string;
  message: string;
  latency_ms?: number;
  details?: Record<string, any>;
}

export interface SyncResult {
  connector_id: string;
  status: string;
  imported_workspaces: number;
  imported_reports: number;
  imported_models: number;
  updated_assets: number;
  skipped_assets: number;
  errors: string[];
  duration_ms: number;
}

export interface MonitoringSummary {
  monitoring_active: boolean;
  total_jobs_executed: number;
  successful_jobs: number;
  failed_jobs: number;
  latest_run?: {
    job_id?: string;
    job_type?: string;
    status?: string;
    started_at?: string;
    duration_ms?: number;
  };
  alerts: {
    unresolved_critical: number;
    unresolved_high: number;
    acknowledged: number;
    resolved: number;
  };
}

export interface MonitoringJob {
  job_id: string;
  job_type: string;
  status: "RUNNING" | "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED";
  started_at: string;
  completed_at?: string;
  duration_ms: number;
  records_processed: number;
  findings_generated: number;
  findings_resolved: number;
  errors?: string;
  source_connector?: string;
  details_json?: string;
}

export interface GovernanceAlert {
  alert_id: string;
  finding_id: string;
  rule_id: string;
  target_entity_type: string;
  target_entity_id: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "NEW" | "ACKNOWLEDGED" | "RESOLVED";
  title: string;
  explanation: string;
  recommended_action: string;
  created_at: string;
  acknowledged_at?: string;
  acknowledged_by?: string;
  acknowledgement_rationale?: string;
  resolved_at?: string;
}

export interface AlertsSummary {
  total_active_alerts: number;
  by_severity: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  by_status: {
    NEW: number;
    ACKNOWLEDGED: number;
    RESOLVED: number;
  };
}

export interface DashboardTelemetry {
  role: string;
  actor_id: string;
  actor_name: string;
  scope_label: string;
  scope_type: string;
  is_admin?: boolean;

  // Requester fields
  my_requests_count?: number;
  my_pending_approvals_count?: number;
  my_approved_requests_count?: number;
  trusted_assets_count?: number;
  recent_requests?: Array<{
    request_id: string;
    prompt: string;
    status: string;
    created_at: string;
  }>;
  my_approvals?: Array<{
    approval_id: string;
    title: string;
    target_entity_id: string;
    status: string;
    action_type: string;
    created_at: string;
  }>;

  // Asset Owner fields
  assigned_assets_count?: number;
  endorsement_breakdown?: {
    certified: number;
    promoted: number;
    none: number;
  };
  active_findings_count?: number;
  critical_findings_count?: number;
  high_findings_count?: number;
  assigned_alerts_count?: number;
  pending_approvals_count?: number;
  assigned_assets?: Array<{
    asset_id: string;
    asset_name: string;
    platform: string;
    endorsement: string;
    lifecycle_status: string;
    estimated_audience: number;
  }>;
  pending_approvals?: Array<{
    approval_id: string;
    title: string;
    target_entity_id: string;
    action_type: string;
    requester_id: string;
    created_at: string;
  }>;

  // Domain Steward fields
  domain_assets_count?: number;
  domain_models_count?: number;
  ai_ready_models_count?: number;
  ai_readiness_pct?: number;
  canonical_kpis_count?: number;
  domain_findings_count?: number;
  pending_domain_reviews_count?: number;
  domain_approvals?: Array<{
    approval_id: string;
    title: string;
    target_entity_id: string;
    action_type: string;
    requester_id: string;
    created_at: string;
  }>;
  domain_assets_sample?: Array<{
    asset_id: string;
    asset_name: string;
    product_scope: string;
    market_scope: string;
    endorsement: string;
  }>;

  // Governance Reviewer / Admin fields
  total_assets?: number;
  certified_assets?: number;
  total_active_findings?: number;
  findings_by_severity?: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  total_pending_approvals?: number;
  governance_reviewer_pending?: number;
  total_tableau_candidates?: number;
  avoided_migration_effort_pct?: number;
  platform_composition?: {
    power_bi: number;
    tableau: number;
  };
}


