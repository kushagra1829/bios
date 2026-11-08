"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ShieldAlert,
  BarChart3,
  CheckSquare,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  Activity,
  ArrowUpRight,
  Bell,
  Clock,
  Layers,
  Database,
  FileCheck,
  UserCheck,
  FileCode2,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/components/layout/Shell";
import { DashboardTelemetry } from "@/lib/types";

// Semantic Color Palette
const COLORS = {
  critical: "#DC5252",
  high: "#E5A12B",
  medium: "#3478F6",
  low: "#16A085",
  powerBi: "#F2C811",
  tableau: "#3478F6",
  trust: "#16A085",
  midnight: "#142438",
};

export default function DashboardPage() {
  const { actorRole, actorId } = useAuth();
  const [telemetry, setTelemetry] = useState<DashboardTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTelemetry() {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getDashboardTelemetry();
        setTelemetry(data);
      } catch (err: any) {
        setError(err.message || "Failed to load role-scoped telemetry.");
      } finally {
        setLoading(false);
      }
    }

    loadTelemetry();
  }, [actorRole, actorId]);

  // Chart data for Governance Reviewer
  const criticalFindings = telemetry?.findings_by_severity?.critical ?? 257;
  const highFindings = telemetry?.findings_by_severity?.high ?? 366;
  const mediumFindings = telemetry?.findings_by_severity?.medium ?? 361;
  const lowFindings = telemetry?.findings_by_severity?.low ?? 121;

  const severityChartData = [
    { name: "Critical", count: criticalFindings, color: COLORS.critical },
    { name: "High", count: highFindings, color: COLORS.high },
    { name: "Medium", count: mediumFindings, color: COLORS.medium },
    { name: "Low", count: lowFindings, color: COLORS.low },
  ];

  const migrationChartData = [
    { pathway: "Consolidate", assets: 30, fill: "#3478F6" },
    { pathway: "Fix Before", assets: 20, fill: "#E5A12B" },
    { pathway: "Retire Instead", assets: 16, fill: "#DC5252" },
    { pathway: "Direct Migrate", assets: 13, fill: "#16A085" },
    { pathway: "Hold Review", assets: 15, fill: "#8884D8" },
  ];

  const platformMixData = [
    { platform: "Power BI", certified: 36, promoted: 42, selfService: 188 },
    { platform: "Tableau", certified: 12, promoted: 18, selfService: 64 },
  ];

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {error && (
        <div className="p-4 rounded-xl bg-critical-50 border border-critical-200 text-critical-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 1. REQUESTER / BUSINESS ANALYST COMMAND CENTER                            */}
      {/* ========================================================================= */}
      {actorRole === "REQUESTER" && (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
                  Business Analytics & Request Hub
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 text-xs font-semibold border border-slate-200">
                  {telemetry?.scope_label ?? "Individual Business Scope"}
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">
                Submit natural-language analytics inquiries, track your personal approvals, and discover trusted enterprise BI assets.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/assistant"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                New Analytics Request
              </Link>
              <Link
                href="/assets"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 shadow-sm transition-colors"
              >
                <BarChart3 className="w-3.5 h-3.5 text-trust" />
                Browse Catalog
              </Link>
            </div>
          </div>

          {/* 4 Requester KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  My Requests
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-intelligence flex items-center justify-center">
                  <Sparkles className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.my_requests_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Inquiries Processed</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Pending Approvals
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                  <Clock className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-amber-600">
                {loading ? "..." : telemetry?.my_pending_approvals_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Awaiting Human Review</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Approved Solutions
                </span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-trust flex items-center justify-center">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-trust">
                {loading ? "..." : telemetry?.my_approved_requests_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Approved for Use</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Trusted Catalog
                </span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <BarChart3 className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.trusted_assets_count ?? 48}
              </div>
              <div className="mt-1 text-xs text-gray-500">Certified Reports Available</div>
            </div>
          </div>

          {/* Quick Analytics Intake Banner */}
          <div className="p-6 rounded-2xl bg-gradient-to-r from-midnight-900 to-midnight-800 text-white flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-intelligence-300" />
                <span className="text-xs font-bold text-intelligence-300 uppercase tracking-wider">
                  AI-Powered Analytics Assistant
                </span>
              </div>
              <h3 className="text-lg font-bold">Have a business question or need a new dashboard?</h3>
              <p className="text-xs text-midnight-200 max-w-xl">
                BIOS checks existing analytics assets and approved KPIs before proposing work, preventing redundant report duplication.
              </p>
            </div>
            <Link
              href="/assistant"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-intelligence text-white text-xs font-bold hover:bg-intelligence-600 shadow-md transition-colors shrink-0"
            >
              Ask Analytics Assistant
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* Recent Inquiries List */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                <Clock className="w-4 h-4 text-intelligence" />
                My Recent Analytics Requests & Adjudications
              </h3>
              <Link href="/assistant" className="text-xs font-semibold text-intelligence hover:underline">
                View All In Assistant
              </Link>
            </div>

            {telemetry?.recent_requests && telemetry.recent_requests.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {telemetry.recent_requests.map((r) => (
                  <div key={r.request_id} className="py-3 flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-gray-700">{r.request_id}</span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded uppercase bg-emerald-100 text-emerald-800">
                          {r.status}
                        </span>
                      </div>
                      <p className="text-xs text-gray-800 font-medium">{r.prompt}</p>
                    </div>
                    <Link
                      href={`/assistant`}
                      className="shrink-0 p-1.5 text-gray-400 hover:text-midnight-900 rounded hover:bg-gray-100 transition-colors"
                    >
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-gray-400">
                No requests submitted yet. Use the Analytics Assistant to submit your first inquiry.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. ASSET OWNER COMMAND CENTER                                             */}
      {/* ========================================================================= */}
      {actorRole === "ASSET_OWNER" && (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
                  Asset Ownership & Governance Hub
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-900 text-xs font-semibold border border-blue-200">
                  {telemetry?.scope_label ?? "Assigned Assets Custody"}
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">
                Manage your assigned analytics assets, resolve governance violations, and authorize change requests.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/approvals"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors"
              >
                <CheckSquare className="w-3.5 h-3.5" />
                Review Approvals ({telemetry?.pending_approvals_count ?? 0})
              </Link>
              <Link
                href="/alerts"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 shadow-sm transition-colors"
              >
                <Bell className="w-3.5 h-3.5 text-rose-600" />
                Assigned Alerts ({telemetry?.assigned_alerts_count ?? 0})
              </Link>
            </div>
          </div>

          {/* Asset Owner KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Assigned Assets
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-intelligence flex items-center justify-center">
                  <BarChart3 className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.assigned_assets_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {telemetry?.endorsement_breakdown?.certified ?? 0} Certified · {telemetry?.endorsement_breakdown?.promoted ?? 0} Promoted
              </div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Pending Approvals
                </span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-intelligence flex items-center justify-center">
                  <CheckSquare className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-indigo-700">
                {loading ? "..." : telemetry?.pending_approvals_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Requires Owner Review</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Active Findings
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-warning flex items-center justify-center">
                  <ShieldAlert className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.active_findings_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-critical font-medium">
                {telemetry?.critical_findings_count ?? 0} Critical Violations
              </div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Active Alerts
                </span>
                <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                  <Bell className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-rose-600">
                {loading ? "..." : telemetry?.assigned_alerts_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Remediation Telemetry</div>
            </div>
          </div>

          {/* Assigned Assets Table */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-intelligence" />
                My Assigned Analytics Assets
              </h3>
              <Link href="/assets" className="text-xs font-semibold text-intelligence hover:underline">
                Catalog ({telemetry?.assigned_assets_count ?? 0})
              </Link>
            </div>

            {telemetry?.assigned_assets && telemetry.assigned_assets.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {telemetry.assigned_assets.map((a) => (
                  <div key={a.asset_id} className="py-3 flex items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-gray-900">{a.asset_id}</span>
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                          {a.platform}
                        </span>
                        <span
                          className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                            a.endorsement === "certified"
                              ? "bg-emerald-100 text-emerald-800"
                              : a.endorsement === "promoted"
                              ? "bg-blue-100 text-blue-800"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {a.endorsement}
                        </span>
                      </div>
                      <p className="text-xs font-medium text-gray-800">{a.asset_name}</p>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-gray-500 hidden sm:inline">
                        Audience: {a.estimated_audience} users
                      </span>
                      <Link
                        href={`/assets/${a.asset_id}`}
                        className="p-1.5 text-gray-400 hover:text-midnight-900 rounded hover:bg-gray-100 transition-colors"
                        title="View asset detail"
                      >
                        <ArrowRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-gray-400">
                No assets currently assigned to this ownership custody profile.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. DOMAIN STEWARD COMMAND CENTER                                          */}
      {/* ========================================================================= */}
      {actorRole === "DOMAIN_STEWARD" && (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
                  Domain Stewardship Command Center
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 text-xs font-semibold border border-slate-200">
                  {telemetry?.scope_label ?? "Domain Scope"}
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">
                Domain-level portfolio oversight, semantic model AI-readiness verification, and KPI definition consistency.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/approvals"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors"
              >
                <CheckSquare className="w-3.5 h-3.5" />
                Domain Reviews ({telemetry?.pending_domain_reviews_count ?? 0})
              </Link>
              <Link
                href="/artifacts"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 shadow-sm transition-colors"
              >
                <FileCode2 className="w-3.5 h-3.5 text-trust" />
                Artifact Studio
              </Link>
            </div>
          </div>

          {/* Domain Steward KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Domain Assets
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-intelligence flex items-center justify-center">
                  <BarChart3 className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.domain_assets_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">In Authorized Domain</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Semantic Models
                </span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-trust flex items-center justify-center">
                  <Layers className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.domain_models_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-trust font-medium">
                {telemetry?.ai_readiness_pct ?? 0}% AI-Ready Architecture
              </div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Canonical KPIs
                </span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <FileCheck className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                {loading ? "..." : telemetry?.canonical_kpis_count ?? 15}
              </div>
              <div className="mt-1 text-xs text-gray-500">Governed Enterprise Metric Definitions</div>
            </div>

            <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Pending Reviews
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                  <CheckSquare className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2 text-3xl font-extrabold text-amber-600">
                {loading ? "..." : telemetry?.pending_domain_reviews_count ?? 0}
              </div>
              <div className="mt-1 text-xs text-gray-500">Steward Queue Pending</div>
            </div>
          </div>

          {/* Domain Approvals Queue */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-intelligence" />
                Domain Approval Requests Requiring Review
              </h3>
              <Link href="/approvals" className="text-xs font-semibold text-intelligence hover:underline">
                Approvals Workspace
              </Link>
            </div>

            {telemetry?.domain_approvals && telemetry.domain_approvals.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {telemetry.domain_approvals.map((a) => (
                  <div key={a.approval_id} className="py-3 flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-gray-900">{a.approval_id}</span>
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-800">
                          {a.action_type}
                        </span>
                        <span className="font-mono text-[11px] text-gray-500">Target: {a.target_entity_id}</span>
                      </div>
                      <p className="text-xs font-medium text-gray-800">{a.title}</p>
                      <p className="text-[11px] text-gray-400">Submitted by: {a.requester_id}</p>
                    </div>

                    <Link
                      href={`/approvals`}
                      className="shrink-0 px-3 py-1.5 rounded bg-slate-100 hover:bg-intelligence hover:text-white text-xs font-semibold text-gray-700 transition-colors"
                    >
                      Adjudicate
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-gray-400">
                Zero active approval requests pending for domain {telemetry?.scope_label}.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. BI GOVERNANCE REVIEWER / BIOS ADMIN COMMAND CENTER                     */}
      {/* ========================================================================= */}
      {(actorRole === "BI_GOVERNANCE_REVIEWER" || actorRole === "BIOS_ADMIN") && (
        <div className="space-y-8">
          {/* Header with Enterprise Positioning */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
                  Enterprise Intelligence Command Center
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 text-xs font-semibold border border-slate-200">
                  {telemetry?.scope_label ?? "Enterprise Governance Scope (Global)"}
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">
                Consolidated executive telemetry across 360 enterprise analytics assets, 8 deterministic governance rules, and 94 legacy migration candidates.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/assistant"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                AI Analytics Assistant
              </Link>
              <Link
                href="/approvals"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 shadow-sm transition-colors"
              >
                <CheckSquare className="w-3.5 h-3.5 text-trust" />
                Approvals Queue ({loading ? "..." : telemetry?.total_pending_approvals ?? 120})
              </Link>
            </div>
          </div>

          {/* Continuous Governance & Operational Focus Ribbon */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Governance & Compliance */}
            <Link
              href="/governance"
              className="p-3.5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-gray-300 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center">
                  <ShieldAlert className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                    Governance & Rules
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-semibold text-amber-700 bg-amber-50">
                      8 Rules
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-medium">
                    {loading ? "..." : telemetry?.total_active_findings ?? 1105} Active Findings
                  </div>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-gray-900 group-hover:translate-x-0.5 transition-all" />
            </Link>

            {/* Continuous Monitoring Engine */}
            <Link
              href="/monitoring"
              className="p-3.5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-gray-300 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-900">
                    Continuous Governance
                  </div>
                  <div className="text-[11px] text-gray-500 font-medium">
                    Continuous automated checks
                  </div>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-gray-900 group-hover:translate-x-0.5 transition-all" />
            </Link>

            {/* Actionable Alerts */}
            <Link
              href="/alerts"
              className="p-3.5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-gray-300 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-700 flex items-center justify-center">
                  <Bell className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                    Alert Centre
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
                      {telemetry?.findings_by_severity?.critical ?? 257} Critical
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-medium">
                    Remediation & Review Queue
                  </div>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-gray-900 group-hover:translate-x-0.5 transition-all" />
            </Link>

            {/* Estate Modernization Backlog */}
            <Link
              href="/lifecycle"
              className="p-3.5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-gray-300 transition-all flex items-center justify-between group"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center">
                  <RefreshCw className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                    Estate Modernization
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-normal text-blue-700 bg-blue-50">
                      48.9% Effort Saved
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-medium">
                    {telemetry?.total_tableau_candidates ?? 94} Legacy Tableau Candidates
                  </div>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-gray-900 group-hover:translate-x-0.5 transition-all" />
            </Link>
          </div>

          {/* 1. Executive Telemetry KPI Cards */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                1. Enterprise Portfolio & Governance Overview
              </h2>
              <span className="text-[11px] text-gray-400 font-mono">
                Dataset Digest: SHA-256 (7d0187...)
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {/* Total Analytics Assets */}
              <Link
                href="/assets"
                className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-intelligence transition-all group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Total Assets
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-blue-50 text-intelligence flex items-center justify-center group-hover:scale-110 transition-transform">
                    <BarChart3 className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                  {loading ? "..." : telemetry?.total_assets ?? 360}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  266 Power BI · 94 Tableau
                </div>
              </Link>

              {/* Endorsed / Certified */}
              <Link
                href="/assets?endorsement=certified"
                className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-trust transition-all group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Certified Tier
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-trust flex items-center justify-center group-hover:scale-110 transition-transform">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-2 text-3xl font-extrabold text-trust">
                  {loading ? "..." : telemetry?.certified_assets ?? 48}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  Governed & Endorsed Reports
                </div>
              </Link>

              {/* Active Governance Findings */}
              <Link
                href="/governance"
                className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-warning transition-all group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Governance Findings
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-amber-50 text-warning flex items-center justify-center group-hover:scale-110 transition-transform">
                    <ShieldAlert className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                  {loading ? "..." : telemetry?.total_active_findings ?? 1105}
                </div>
                <div className="mt-1 text-xs text-critical font-medium">
                  {criticalFindings} Critical · {highFindings} High
                </div>
              </Link>

              {/* Pending Human Approvals */}
              <Link
                href="/approvals"
                className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-intelligence transition-all group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Pending Approvals
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-intelligence flex items-center justify-center group-hover:scale-110 transition-transform">
                    <CheckSquare className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                  {loading ? "..." : telemetry?.total_pending_approvals ?? 120}
                </div>
                <div className="mt-1 text-xs text-intelligence font-medium">
                  {telemetry?.governance_reviewer_pending ?? 56} Reviewer Queue
                </div>
              </Link>

              {/* Migration Backlog */}
              <Link
                href="/lifecycle"
                className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm hover:border-purple-300 transition-all group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Migration Backlog
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <RefreshCw className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-2 text-3xl font-extrabold text-midnight-900">
                  {loading ? "..." : telemetry?.total_tableau_candidates ?? 94}
                </div>
                <div className="mt-1 text-xs text-purple-600 font-medium">
                  48.9% Effort Reduction
                </div>
              </Link>
            </div>
          </section>

          {/* 2. Visualizations: Governance, Migration, and Platform Mix */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider">
              2. Analytics Portfolio & Modernization Intelligence
            </h2>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Chart 1: Governance Findings Severity */}
              <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                  <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-warning" />
                    Findings by Severity
                  </h3>
                  <Link href="/governance" className="text-xs font-semibold text-intelligence flex items-center gap-1 hover:underline">
                    View All <ArrowUpRight className="w-3 h-3" />
                  </Link>
                </div>

                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={severityChartData}
                        dataKey="count"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={45}
                        outerRadius={75}
                        paddingAngle={3}
                      >
                        {severityChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number) => [`${value} findings`, "Count"]} />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: "11px" }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <p className="text-[11px] text-gray-500 text-center">
                  Evaluated across 8 deterministic governance rules (RULE-001 to RULE-008).
                </p>
              </div>

              {/* Chart 2: Migration Rationalization Pathways */}
              <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                  <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-intelligence" />
                    Tableau Migration Rationalization
                  </h3>
                  <Link href="/lifecycle" className="text-xs font-semibold text-intelligence flex items-center gap-1 hover:underline">
                    Backlog <ArrowUpRight className="w-3 h-3" />
                  </Link>
                </div>

                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={migrationChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                      <XAxis dataKey="pathway" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(value: number) => [`${value} assets`, "Total Assets"]} />
                      <Bar dataKey="assets" radius={[4, 4, 0, 0]}>
                        {migrationChartData.map((entry, index) => (
                          <Cell key={`bar-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <p className="text-[11px] text-gray-500 text-center">
                  Replaces blind 1:1 lift-and-shift with governed consolidation and waste elimination.
                </p>
              </div>

              {/* Chart 3: Platform Endorsement Tiers */}
              <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                  <h3 className="text-sm font-bold text-midnight-900 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-trust" />
                    Platform Endorsement Mix
                  </h3>
                  <Link href="/assets" className="text-xs font-semibold text-intelligence flex items-center gap-1 hover:underline">
                    Catalog <ArrowUpRight className="w-3 h-3" />
                  </Link>
                </div>

                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={platformMixData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                      <XAxis dataKey="platform" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: "11px" }} />
                      <Bar dataKey="certified" name="Certified" fill={COLORS.trust} stackId="a" />
                      <Bar dataKey="promoted" name="Promoted" fill={COLORS.medium} stackId="a" />
                      <Bar dataKey="selfService" name="Self-Service" fill="#E2E8F0" stackId="a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <p className="text-[11px] text-gray-500 text-center">
                  Enforces RULE-005: Assets exceeding 500 users require certified models.
                </p>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
