"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  BarChart3,
  ShieldAlert,
  Award,
  Layers,
  User,
  ExternalLink,
  Calendar,
  AlertTriangle,
  GitBranch,
  CheckCircle2,
  Sparkles,
  CheckSquare,
  Clock,
  Server,
  Activity,
} from "lucide-react";
import { api } from "@/lib/api";
import { AnalyticsAsset, GovernanceFinding } from "@/lib/types";

export default function AssetDetailPage() {
  const params = useParams();
  const assetId = params?.assetId as string;

  const [asset, setAsset] = useState<AnalyticsAsset | null>(null);
  const [findings, setFindings] = useState<GovernanceFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!assetId) return;

    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const [assetData, findingsData] = await Promise.all([
          api.getAsset(assetId).catch(() => null),
          api.getGovernanceFindings(100).catch(() => ({ total: 0, findings: [] })),
        ]);

        setAsset(assetData);
        // Filter findings matching this asset
        const assetFindings = (findingsData.findings || []).filter(
          (f) => f.target_entity_id === assetId
        );
        setFindings(assetFindings);
      } catch (err: any) {
        setError(err.message || "Failed to load asset details");
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [assetId]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto py-16 text-center text-sm text-gray-500 space-y-2">
        <div className="w-6 h-6 border-2 border-intelligence border-t-transparent rounded-full animate-spin mx-auto" />
        <div>Loading authoritative catalog telemetry for asset {assetId}...</div>
      </div>
    );
  }

  if (!asset) {
    return (
      <div className="max-w-5xl mx-auto py-16 text-center space-y-4">
        <div className="text-xl font-bold text-midnight-900">Asset Not Found</div>
        <p className="text-sm text-gray-500">No asset with ID {assetId} exists in the enterprise catalog.</p>
        <Link
          href="/assets"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold"
        >
          <ArrowLeft className="w-4 h-4" /> Return to Analytics Portfolio
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Breadcrumb & Navigation */}
      <div>
        <Link
          href="/assets"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-midnight-900 mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Analytics Portfolio
        </Link>

        {/* Hero Card */}
        <div className="p-6 bg-white rounded-xl border border-gray-200 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-sm font-extrabold px-2.5 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">
                  {asset.asset_id}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                    asset.platform === "Power BI"
                      ? "bg-amber-100 text-amber-900 border border-amber-200"
                      : "bg-blue-100 text-blue-900 border border-blue-200"
                  }`}
                >
                  {asset.platform}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                    asset.endorsement === "certified"
                      ? "bg-emerald-100 text-trust border border-emerald-200"
                      : asset.endorsement === "promoted"
                      ? "bg-blue-100 text-intelligence border border-blue-200"
                      : "bg-gray-100 text-gray-700"
                  }`}
                >
                  {asset.endorsement || "None"}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded text-xs font-semibold uppercase ${
                    asset.lifecycle_status === "active"
                      ? "bg-emerald-50 text-emerald-800"
                      : asset.lifecycle_status === "candidate_retire"
                      ? "bg-red-50 text-critical font-bold border border-red-200"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {asset.lifecycle_status}
                </span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-midnight-900 pt-1">
                {asset.asset_name}
              </h1>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2 shrink-0">
              <Link
                href="/assistant"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Analyze in AI Assistant
              </Link>
              <Link
                href="/approvals"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
              >
                <CheckSquare className="w-3.5 h-3.5 text-trust" />
                Change Request
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Metadata, Lineage, and Governance */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Core Attributes & Scope */}
        <div className="lg:col-span-2 space-y-6">
          {/* Metadata Card */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
            <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2">
              Asset Attributes & Governance Scope
            </h2>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-gray-400 block mb-0.5">Product Scope</span>
                <span className="font-semibold text-gray-900">{asset.product_scope || "Unspecified"}</span>
              </div>

              <div>
                <span className="text-gray-400 block mb-0.5">Geographic Market</span>
                <span className="font-semibold text-gray-900">{asset.market_scope || "Global"}</span>
              </div>

              <div>
                <span className="text-gray-400 block mb-0.5">Delivery Model</span>
                <span className="font-semibold text-gray-900 capitalize">{asset.delivery_model || "Central BI"}</span>
              </div>

              <div>
                <span className="text-gray-400 block mb-0.5">Estimated Audience Reach</span>
                <span className="font-mono font-bold text-gray-900">
                  {asset.estimated_audience ? `${asset.estimated_audience.toLocaleString()} users` : "Unmonitored"}
                </span>
              </div>

              <div>
                <span className="text-gray-400 block mb-0.5">Workspace</span>
                <span className="font-mono text-gray-800">{asset.workspace_id || "WS-DEFAULT"}</span>
              </div>

              <div>
                <span className="text-gray-400 block mb-0.5">Data Classification</span>
                <span className="font-semibold uppercase text-slate-700">{asset.classification || "Internal"}</span>
              </div>
            </div>
          </div>

          {/* Lineage & Semantic Dependencies */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-4">
            <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2 flex items-center gap-2">
              <GitBranch className="w-3.5 h-3.5 text-intelligence" />
              Lineage & Semantic Model Dependencies
            </h2>

            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-900">Upstream Semantic Model</span>
                {asset.model_id ? (
                  <span className="font-mono font-bold text-intelligence bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                    {asset.model_id}
                  </span>
                ) : (
                  <span className="text-critical font-bold bg-red-50 px-2 py-0.5 rounded">Missing Model ID</span>
                )}
              </div>
              <p className="text-slate-600 leading-relaxed">
                {asset.model_id
                  ? `Report queries enterprise semantic model ${asset.model_id}. Complies with RULE-004 structural lineage requirement.`
                  : "Asset lacks registered semantic model lineage in catalog. Triggers RULE-004 governance blocker."}
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Ownership & Active Findings */}
        <div className="space-y-6">
          {/* Ownership Card */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-3">
            <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-trust" />
              Accountable Business Owner
            </h2>

            <div className="text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Owner ID:</span>
                <span className="font-mono font-bold text-gray-900">
                  {asset.owner_id || <span className="text-critical">Unassigned</span>}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-gray-500">Governance Status:</span>
                {asset.owner_id ? (
                  <span className="text-trust font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Assigned
                  </span>
                ) : (
                  <span className="text-critical font-bold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> RULE-003 Violation
                  </span>
                )}
              </div>
              <p className="text-[11px] text-gray-500 pt-1 border-t border-gray-100">
                Control N4 enforces live owner identity verification before change approvals are processed.
              </p>
            </div>
          </div>

          {/* Governance Findings Card */}
          <div className="p-5 rounded-xl bg-white border border-gray-200 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b border-gray-100 pb-2">
              <h2 className="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-warning" />
                Active Findings ({findings.length})
              </h2>
              <Link href="/governance" className="text-[11px] font-semibold text-intelligence hover:underline">
                View All
              </Link>
            </div>

            {findings.length === 0 ? (
              <p className="text-xs text-trust font-medium py-3 text-center flex items-center justify-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> Zero active governance findings.
              </p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {findings.map((f) => (
                  <div key={f.finding_id} className="p-2.5 rounded bg-gray-50 border border-gray-200 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-gray-800">{f.rule_id}</span>
                      <span
                        className={`text-[9px] uppercase font-bold px-1.5 py-0.2 rounded ${
                          f.severity === "critical"
                            ? "bg-red-100 text-critical"
                            : f.severity === "high"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {f.severity}
                      </span>
                    </div>
                    <p className="text-gray-700 font-medium text-[11px]">{f.title}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
