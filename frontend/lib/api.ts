import {
  HealthResponse,
  GovernanceRule,
  GovernanceSummary,
  GovernanceFinding,
  AnalyticsAsset,
  SemanticModel,
  CanonicalKpi,
  AssistantWorkflowResponse,
  ApprovalRequest,
  ApprovalQueueSummary,
  ApprovalTransition,
  MigrationCandidate,
  MigrationSummary,
  DashboardSpecification,
  GeneratedArtifact,
  AuditEvent,
  IntegrationStatus,
  ConnectionTestResult,
  SyncResult,
  MonitoringSummary,
  MonitoringJob,
  GovernanceAlert,
  AlertsSummary,
  DashboardTelemetry,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? "" : "http://127.0.0.1:8000");

let currentAuth = {
  actorId: "OWN-001",
  actorRole: "BI_GOVERNANCE_REVIEWER",
};

export function setApiAuth(actorId: string, actorRole: string) {
  currentAuth = { actorId, actorRole };
}

async function fetcher<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Actor-Id": currentAuth.actorId,
        "X-Actor-Role": currentAuth.actorRole,
        ...(options?.headers || {}),
      },
    });

    if (!res.ok) {
      let errorMsg = res.statusText ? `HTTP Error ${res.status}: ${res.statusText}` : `HTTP Error ${res.status}`;
      try {
        const errorJson = await res.json();
        if (errorJson.details && Array.isArray(errorJson.details)) {
          errorMsg = errorJson.details
            .map((d: any) => `${d.loc?.slice(-1)[0] || 'field'}: ${d.msg}`)
            .join('; ');
        } else if (errorJson.error) {
          errorMsg = errorJson.error;
        } else if (errorJson.detail) {
          errorMsg = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // Fallback to text status
      }
      if (errorMsg.trim().endsWith(":") || errorMsg === `HTTP Error ${res.status}`) {
        errorMsg = `HTTP Error ${res.status}: Request could not be completed. Please retry.`;
      }
      const err = new Error(errorMsg) as any;
      err.status = res.status;
      throw err;
    }

    return await res.json();
  } catch (err: any) {
    if (err.status) throw err;
    // Network / connection error
    const target = API_BASE || "http://127.0.0.1:8000";
    const netErr = new Error(`Connection to BIOS backend (${target}) failed. Please ensure the backend is running on port 8000.`) as any;
    netErr.status = 503;
    throw netErr;
  }
}

export const api = {
  // Command Center Role-Scoped Telemetry
  async getDashboardTelemetry(): Promise<DashboardTelemetry> {
    return fetcher<DashboardTelemetry>("/api/v1/dashboard/telemetry");
  },

  // System Health
  async getHealth(): Promise<HealthResponse> {
    return fetcher<HealthResponse>("/health");
  },

  // Governance
  async getGovernanceRules(): Promise<GovernanceRule[]> {
    return fetcher<GovernanceRule[]>("/api/v1/governance/rules");
  },

  async getGovernanceRule(ruleId: string): Promise<GovernanceRule> {
    return fetcher<GovernanceRule>(`/api/v1/governance/rules/${ruleId}`);
  },

  async getGovernanceSummary(): Promise<GovernanceSummary> {
    return fetcher<GovernanceSummary>("/api/v1/governance/summary");
  },

  async getGovernanceFindings(limit = 100, severity?: string, ruleId?: string): Promise<{ total: number; findings: GovernanceFinding[] }> {
    let query = `?limit=${limit}`;
    if (severity) query += `&severity=${encodeURIComponent(severity)}`;
    if (ruleId) query += `&rule_id=${encodeURIComponent(ruleId)}`;
    return fetcher<{ total: number; findings: GovernanceFinding[] }>(`/api/v1/governance/findings${query}`);
  },

  async evaluateGovernance(): Promise<{ status: string; total_findings: number; execution_time_ms: number }> {
    return fetcher<{ status: string; total_findings: number; execution_time_ms: number }>("/api/v1/governance/evaluate", {
      method: "POST",
    });
  },

  // Catalog
  async getAssets(limit = 400, skip = 0, platform?: string, product?: string, endorsement?: string, search?: string): Promise<AnalyticsAsset[]> {
    let query = `?limit=${limit}&skip=${skip}`;
    if (platform) query += `&platform=${encodeURIComponent(platform)}`;
    if (product) query += `&product=${encodeURIComponent(product)}`;
    if (endorsement) query += `&endorsement=${encodeURIComponent(endorsement)}`;
    if (search) query += `&search=${encodeURIComponent(search)}`;
    const res = await fetcher<any>(`/api/v1/assets${query}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  },

  async getAsset(assetId: string): Promise<AnalyticsAsset> {
    return fetcher<AnalyticsAsset>(`/api/v1/assets/${assetId}`);
  },

  async getSemanticModels(limit = 100): Promise<SemanticModel[]> {
    const res = await fetcher<any>(`/api/v1/semantic-models?limit=${limit}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  },

  async getKpis(limit = 100): Promise<CanonicalKpi[]> {
    const res = await fetcher<any>(`/api/v1/kpis?limit=${limit}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  },

  // Assistant & Multi-Agent Orchestration
  async submitAssistantRequest(prompt: string, requester = "FrontendUser"): Promise<AssistantWorkflowResponse> {
    return fetcher<AssistantWorkflowResponse>("/api/v1/assistant/requests", {
      method: "POST",
      body: JSON.stringify({ prompt, requester }),
    });
  },

  async getAssistantRequests(limit = 20): Promise<{ requests: AssistantWorkflowResponse[]; total: number }> {
    return fetcher<{ requests: AssistantWorkflowResponse[]; total: number }>(`/api/v1/assistant/requests?limit=${limit}`);
  },

  async getAssistantRequest(requestId: string): Promise<AssistantWorkflowResponse> {
    return fetcher<AssistantWorkflowResponse>(`/api/v1/assistant/requests/${requestId}`);
  },

  // Approvals & Lifecycle
  async getApprovals(status?: string, requiredRole?: string, search?: string): Promise<ApprovalRequest[]> {
    let query = "";
    const params = [];
    if (status) params.push(`status=${encodeURIComponent(status)}`);
    if (requiredRole) params.push(`required_role=${encodeURIComponent(requiredRole)}`);
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    if (params.length) query = `?${params.join("&")}`;
    return fetcher<ApprovalRequest[]>(`/api/v1/approvals${query}`);
  },

  async getApproval(approvalId: string): Promise<ApprovalRequest> {
    return fetcher<ApprovalRequest>(`/api/v1/approvals/${approvalId}`);
  },

  async getApprovalSummary(): Promise<ApprovalQueueSummary> {
    return fetcher<ApprovalQueueSummary>("/api/v1/approvals/summary");
  },

  async submitApprovalRequest(payload: {
    title: string;
    action_type: string;
    description: string;
    target_entity_type?: string;
    target_entity_id?: string;
    recommendation_ref?: string;
    evidence_snapshot?: Record<string, any>;
    blockers?: string[];
    warnings?: string[];
  }): Promise<ApprovalRequest> {
    return fetcher<ApprovalRequest>("/api/v1/approvals", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async approveRequest(approvalId: string, actorId: string, actorRole: string, reason: string): Promise<ApprovalRequest> {
    return fetcher<ApprovalRequest>(`/api/v1/approvals/${approvalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId, actor_role: actorRole, decision: "APPROVED", reason }),
    });
  },

  async rejectRequest(approvalId: string, actorId: string, actorRole: string, reason: string): Promise<ApprovalRequest> {
    return fetcher<ApprovalRequest>(`/api/v1/approvals/${approvalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId, actor_role: actorRole, decision: "REJECTED", reason }),
    });
  },

  async requestChanges(approvalId: string, actorId: string, actorRole: string, reason: string): Promise<ApprovalRequest> {
    return fetcher<ApprovalRequest>(`/api/v1/approvals/${approvalId}/request-changes`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId, actor_role: actorRole, decision: "CHANGES_REQUESTED", reason }),
    });
  },

  async getApprovalHistory(approvalId: string): Promise<ApprovalTransition[]> {
    return fetcher<ApprovalTransition[]>(`/api/v1/approvals/${approvalId}/history`);
  },

  // Migration & Lifecycle
  async getMigrationCandidates(action?: string, complexity?: string): Promise<MigrationCandidate[]> {
    const params = [];
    if (action) params.push(`action=${encodeURIComponent(action)}`);
    if (complexity) params.push(`complexity=${encodeURIComponent(complexity)}`);
    const query = params.length ? `?${params.join("&")}` : "";
    return fetcher<MigrationCandidate[]>(`/api/v1/migration/recommendations${query}`);
  },

  async getMigrationSummary(): Promise<MigrationSummary> {
    return fetcher<MigrationSummary>("/api/v1/migration/summary");
  },

  async evaluateLifecycle(): Promise<{ status: string; evaluated_assets: number }> {
    return fetcher<{ status: string; evaluated_assets: number }>("/api/v1/lifecycle/evaluate", {
      method: "POST",
    });
  },

  // Power BI Artifact Factory
  async getArtifacts(): Promise<GeneratedArtifact[]> {
    return fetcher<GeneratedArtifact[]>("/api/v1/artifacts");
  },

  async getArtifact(artifactId: string): Promise<GeneratedArtifact> {
    return fetcher<GeneratedArtifact>(`/api/v1/artifacts/${artifactId}`);
  },

  async getArtifactFiles(artifactId: string): Promise<{ files: string[] }> {
    return fetcher<{ files: string[] }>(`/api/v1/artifacts/${artifactId}/files`);
  },

  async generateArtifact(payload: {
    spec?: any;
    spec_id?: string;
    request_id?: string;
    approval_id?: string;
    actor_id?: string;
    actor_role?: string;
    output_format?: string;
    force?: boolean;
  }): Promise<GeneratedArtifact> {
    return fetcher<GeneratedArtifact>("/api/v1/artifacts/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Audit Events
  async getAuditEvents(limit = 50, entityId?: string): Promise<AuditEvent[]> {
    let query = `?limit=${limit}`;
    if (entityId) query += `&target_entity_id=${encodeURIComponent(entityId)}`;
    return fetcher<AuditEvent[]>(`/api/v1/audit/events${query}`);
  },

  // BI Integrations (Power BI & Tableau)
  async getIntegrations(): Promise<IntegrationStatus[]> {
    return fetcher<IntegrationStatus[]>("/api/v1/integrations");
  },

  async getIntegration(connectorId: string): Promise<IntegrationStatus> {
    return fetcher<IntegrationStatus>(`/api/v1/integrations/${connectorId}`);
  },

  async testIntegration(connectorId: string): Promise<ConnectionTestResult> {
    return fetcher<ConnectionTestResult>(`/api/v1/integrations/${connectorId}/test`, {
      method: "POST",
    });
  },

  async syncIntegration(connectorId: string, force = false): Promise<SyncResult> {
    return fetcher<SyncResult>(`/api/v1/integrations/${connectorId}/sync?force=${force}`, {
      method: "POST",
    });
  },

  // Continuous Governance Monitoring
  async getMonitoringSummary(): Promise<MonitoringSummary> {
    return fetcher<MonitoringSummary>("/api/v1/monitoring/summary");
  },

  async getMonitoringJobs(jobType?: string, status?: string, limit = 50, offset = 0): Promise<MonitoringJob[]> {
    const params = [`limit=${limit}`, `offset=${offset}`];
    if (jobType) params.push(`job_type=${encodeURIComponent(jobType)}`);
    if (status) params.push(`status=${encodeURIComponent(status)}`);
    return fetcher<MonitoringJob[]>(`/api/v1/monitoring/jobs?${params.join("&")}`);
  },

  async triggerMonitoringJob(jobType = "FULL_CONTINUOUS_SCAN", actor = "ADMIN_MANUAL"): Promise<MonitoringJob> {
    return fetcher<MonitoringJob>("/api/v1/monitoring/jobs/run", {
      method: "POST",
      body: JSON.stringify({ job_type: jobType, actor }),
    });
  },

  // Governance Alert Center
  async getAlerts(severity?: string, status?: string, ruleId?: string, search?: string, limit = 100, offset = 0): Promise<GovernanceAlert[]> {
    const params = [`limit=${limit}`, `offset=${offset}`];
    if (severity) params.push(`severity=${encodeURIComponent(severity)}`);
    if (status) params.push(`status=${encodeURIComponent(status)}`);
    if (ruleId) params.push(`rule_id=${encodeURIComponent(ruleId)}`);
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    return fetcher<GovernanceAlert[]>(`/api/v1/alerts?${params.join("&")}`);
  },

  async getAlertsSummary(): Promise<AlertsSummary> {
    return fetcher<AlertsSummary>("/api/v1/alerts/summary");
  },

  async getAlert(alertId: string): Promise<GovernanceAlert> {
    return fetcher<GovernanceAlert>(`/api/v1/alerts/${alertId}`);
  },

  async acknowledgeAlert(alertId: string, actorId: string, actorRole: string, rationale: string): Promise<GovernanceAlert> {
    return fetcher<GovernanceAlert>(`/api/v1/alerts/${alertId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ actor_id: actorId, actor_role: actorRole, rationale }),
    });
  },
};

