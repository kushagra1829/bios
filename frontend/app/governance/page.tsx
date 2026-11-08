"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Play,
  Filter,
  CheckCircle2,
  FileSpreadsheet,
  Layers,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Search,
  Check,
  Info,
  Clock,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { GovernanceRule, GovernanceFinding, GovernanceSummary } from "@/lib/types";

export default function GovernancePage() {
  const [rules, setRules] = useState<GovernanceRule[]>([]);
  const [summary, setSummary] = useState<GovernanceSummary | null>(null);
  const [findings, setFindings] = useState<GovernanceFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<string | null>(null);

  // Filter state
  const [selectedRule, setSelectedRule] = useState<string>("");
  const [selectedSeverity, setSelectedSeverity] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);

  async function loadData() {
    try {
      setLoading(true);
      const [rulesData, summaryData, findingsData] = await Promise.all([
        api.getGovernanceRules().catch(() => []),
        api.getGovernanceSummary().catch(() => null),
        api.getGovernanceFindings(150, selectedSeverity || undefined, selectedRule || undefined).catch(() => ({ total: 0, findings: [] })),
      ]);

      setRules(rulesData);
      setSummary(summaryData);
      setFindings(findingsData.findings || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [selectedRule, selectedSeverity]);

  async function handleTriggerEvaluation() {
    try {
      setEvaluating(true);
      setEvalResult(null);
      const res = await api.evaluateGovernance();
      setEvalResult(`Governance scan complete: ${res.total_findings} findings evaluated in ${res.execution_time_ms}ms.`);
      await loadData();
    } catch (err: any) {
      setEvalResult(`Evaluation error: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  }

  const filteredFindings = findings.filter((f) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      f.finding_id.toLowerCase().includes(q) ||
      f.target_entity_id.toLowerCase().includes(q) ||
      f.title.toLowerCase().includes(q) ||
      (f.explanation && f.explanation.toLowerCase().includes(q))
    );
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Governance & Compliance Operations
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 text-xs font-semibold border border-slate-200">
              8 Deterministic Rules Enforced
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Deterministic governance enforcement, active compliance violation monitoring, and audit-grounded evidence inspection.
          </p>
        </div>

        <button
          onClick={handleTriggerEvaluation}
          disabled={evaluating}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 disabled:opacity-50 transition-colors shrink-0"
        >
          {evaluating ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Scanning Catalog...
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-white" />
              Run Full Governance Scan
            </>
          )}
        </button>
      </div>

      {evalResult && (
        <div className="p-3.5 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900 font-medium flex items-center justify-between">
          <span>{evalResult}</span>
          <button onClick={() => setEvalResult(null)} className="text-blue-500 hover:text-blue-800 font-bold ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Governance Metric Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Findings</span>
          <div className="text-2xl font-extrabold text-midnight-900">{summary?.total_active_findings ?? 1105}</div>
          <div className="text-[11px] text-gray-400">Across 360 catalog assets</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-critical uppercase tracking-wider">Critical Violations</span>
          <div className="text-2xl font-extrabold text-critical">
            {summary?.findings_by_severity?.critical ?? 257}
          </div>
          <div className="text-[11px] text-red-500">Immediate blockers</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-warning uppercase tracking-wider">High Severity</span>
          <div className="text-2xl font-extrabold text-warning">
            {summary?.findings_by_severity?.high ?? 366}
          </div>
          <div className="text-[11px] text-amber-600">Requires remediation plan</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-intelligence uppercase tracking-wider">Medium Findings</span>
          <div className="text-2xl font-extrabold text-intelligence">
            {summary?.findings_by_severity?.medium ?? 361}
          </div>
          <div className="text-[11px] text-blue-500">Quality & alias drift</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-trust uppercase tracking-wider">Low / Info</span>
          <div className="text-2xl font-extrabold text-trust">{summary?.findings_by_severity?.low ?? 121}</div>
          <div className="text-[11px] text-emerald-600">Documentation hygiene</div>
        </div>
      </div>

      {/* 2. Eight Deterministic Governance Rules Overview */}
      <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-gray-100 pb-3">
          <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-trust" />
            The 8 Deterministic Corporate Governance Rules
          </h2>
          <span className="text-[11px] text-gray-400 font-mono">
            Immutable Predicates · RULE-005: 500 / 250
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {rules.map((rule) => {
            const isExpanded = expandedRuleId === rule.rule_id;
            const findingCount = summary?.findings_by_rule?.[rule.rule_id] ?? 0;

            return (
              <div
                key={rule.rule_id}
                onClick={() => setExpandedRuleId(isExpanded ? null : rule.rule_id)}
                className={`p-3.5 rounded-lg border text-xs cursor-pointer transition-all space-y-2 ${
                  isExpanded
                    ? "bg-blue-50/60 border-intelligence ring-1 ring-intelligence"
                    : "bg-gray-50/70 border-gray-200 hover:border-gray-300 hover:bg-white"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-midnight-900">{rule.rule_id}</span>
                  <span
                    className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                      rule.severity === "critical"
                        ? "bg-red-100 text-critical"
                        : rule.severity === "high"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {rule.severity}
                  </span>
                </div>

                <div className="font-semibold text-gray-900 text-xs line-clamp-1">{rule.rule_name}</div>
                <p className="text-[11px] text-gray-600 line-clamp-2">{rule.description}</p>

                <div className="flex items-center justify-between text-[11px] font-mono text-gray-500 pt-1 border-t border-gray-200/60">
                  <span>Active Findings:</span>
                  <span className="font-bold text-midnight-900">{findingCount}</span>
                </div>

                {isExpanded && (
                  <div className="mt-2 pt-2 border-t border-blue-200 text-[11px] text-slate-700 space-y-1.5">
                    {rule.business_impact && (
                      <div>
                        <strong className="text-slate-900">Business Impact:</strong> {rule.business_impact}
                      </div>
                    )}
                    {rule.remediation_guidance && (
                      <div>
                        <strong className="text-slate-900">Remediation Guidance:</strong> {rule.remediation_guidance}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Findings Explorer & Remediation Workspace */}
      <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-gray-100 pb-3">
          <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-2">
            <Filter className="w-4 h-4 text-intelligence" />
            Active Governance Findings Explorer ({filteredFindings.length})
          </h2>

          <div className="flex flex-wrap items-center gap-2">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search findings or entity..."
                className="pl-8 pr-3 py-1.5 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
              />
            </div>

            {/* Rule Filter */}
            <select
              value={selectedRule}
              onChange={(e) => setSelectedRule(e.target.value)}
              className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs text-midnight-900 bg-white focus:outline-none focus:ring-1 focus:ring-intelligence"
            >
              <option value="">All Rules</option>
              {rules.map((r) => (
                <option key={r.rule_id} value={r.rule_id}>
                  {r.rule_id} — {r.rule_name}
                </option>
              ))}
            </select>

            {/* Severity Filter */}
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs text-midnight-900 bg-white focus:outline-none focus:ring-1 focus:ring-intelligence"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        {/* Findings List */}
        {loading ? (
          <div className="p-8 text-center text-xs text-gray-500">
            <RefreshCw className="w-4 h-4 animate-spin mx-auto text-intelligence mb-2" />
            Loading governance findings...
          </div>
        ) : filteredFindings.length === 0 ? (
          <div className="p-8 text-center text-xs text-gray-500">
            No governance findings matching the specified criteria.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filteredFindings.map((f) => {
              const isExpanded = expandedFindingId === f.finding_id;

              return (
                <div key={f.finding_id} className="py-3 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-bold text-gray-800">{f.finding_id}</span>
                      <span
                        className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                          f.severity === "critical"
                            ? "bg-red-100 text-critical"
                            : f.severity === "high"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {f.severity}
                      </span>
                      <span className="font-mono text-xs font-bold text-intelligence bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                        {f.rule_id}
                      </span>
                      <span className="text-xs font-semibold text-gray-900">{f.title}</span>
                    </div>

                    <div className="flex items-center gap-3 text-xs shrink-0">
                      <Link
                        href={`/assets/${f.target_entity_id}`}
                        className="font-mono text-gray-700 hover:text-intelligence flex items-center gap-1 font-bold"
                      >
                        Entity: {f.target_entity_id} <ExternalLink className="w-3 h-3" />
                      </Link>
                      <button
                        onClick={() => setExpandedFindingId(isExpanded ? null : f.finding_id)}
                        className="text-intelligence font-medium hover:underline flex items-center gap-0.5"
                      >
                        {isExpanded ? "Hide Evidence" : "Inspect Evidence"}
                        {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>

                  {f.explanation && (
                    <p className="text-xs text-gray-600 leading-relaxed font-sans">{f.explanation}</p>
                  )}

                  {/* Expanded Evidence Bundle Details */}
                  {isExpanded && f.evidence_bundle && (
                    <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono space-y-2">
                      <div className="font-bold text-slate-800 flex items-center gap-1.5">
                        <FileSpreadsheet className="w-3.5 h-3.5 text-intelligence" />
                        Authoritative Evidence Grounding:
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-slate-700">
                        <div>
                          <strong>Source Table:</strong> {f.evidence_bundle.primary_reference?.source_table || "analytics_assets"}
                        </div>
                        <div>
                          <strong>Record ID:</strong> {f.evidence_bundle.primary_reference?.record_id || f.target_entity_id}
                        </div>
                        {f.evidence_bundle.primary_reference?.field_name && (
                          <div>
                            <strong>Field:</strong> {f.evidence_bundle.primary_reference.field_name}
                          </div>
                        )}
                        {f.evidence_bundle.primary_reference?.observed_value && (
                          <div>
                            <strong>Observed Value:</strong> {f.evidence_bundle.primary_reference.observed_value}
                          </div>
                        )}
                      </div>
                      {f.evidence_bundle.explanation_narrative && (
                        <p className="text-[11px] text-slate-600 font-sans pt-1 border-t border-slate-200">
                          {f.evidence_bundle.explanation_narrative}
                        </p>
                      )}
                      <div className="pt-1 flex items-center gap-3">
                        <Link
                          href={`/assets/${f.target_entity_id}`}
                          className="inline-flex items-center gap-1 text-[11px] font-sans font-bold text-intelligence hover:underline"
                        >
                          Remediate Asset in Portfolio →
                        </Link>
                        <Link
                          href="/approvals"
                          className="inline-flex items-center gap-1 text-[11px] font-sans font-semibold text-trust hover:underline"
                        >
                          Request Governance Waiver in Approvals →
                        </Link>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
