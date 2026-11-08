"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  BarChart3,
  Search,
  Filter,
  ArrowUpDown,
  ExternalLink,
  ShieldAlert,
  Award,
  Layers,
  Building2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  User,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { AnalyticsAsset } from "@/lib/types";

export default function AssetsPage() {
  const [assets, setAssets] = useState<AnalyticsAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("");
  const [endorsement, setEndorsement] = useState("");
  const [lifecycleStatus, setLifecycleStatus] = useState("");
  const [productFilter, setProductFilter] = useState("");

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 25;

  useEffect(() => {
    async function loadAssets() {
      try {
        setLoading(true);
        setError(null);
        // Load full 360 catalog
        const data = await api.getAssets(
          360,
          0,
          platform || undefined,
          productFilter || undefined,
          endorsement || undefined
        );
        setAssets(data);
      } catch (err: any) {
        setError(err.message || "Failed to load analytics assets from catalog.");
      } finally {
        setLoading(false);
      }
    }

    loadAssets();
  }, [platform, endorsement, productFilter]);

  const filteredAssets = assets.filter((a) => {
    if (lifecycleStatus && a.lifecycle_status !== lifecycleStatus) return false;
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      a.asset_name.toLowerCase().includes(q) ||
      a.asset_id.toLowerCase().includes(q) ||
      (a.product_scope && a.product_scope.toLowerCase().includes(q)) ||
      (a.market_scope && a.market_scope.toLowerCase().includes(q)) ||
      (a.owner_id && a.owner_id.toLowerCase().includes(q))
    );
  });

  const totalFiltered = filteredAssets.length;
  const totalPages = Math.ceil(totalFiltered / pageSize) || 1;
  const paginatedAssets = filteredAssets.slice((page - 1) * pageSize, page * pageSize);

  // Available unique products for filter dropdown
  const uniqueProducts = Array.from(new Set(assets.map((a) => a.product_scope).filter(Boolean))).sort();

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Enterprise Analytics Portfolio
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-intelligence text-xs font-semibold border border-blue-200">
              360 Total Assets
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Authoritative catalog of 360 analytics reports across Power BI and Tableau with ownership, semantic model lineage, and audience reach telemetry.
          </p>
        </div>

        <Link
          href="/assistant"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-intelligence text-white text-xs font-bold shadow-sm hover:bg-intelligence-600 transition-colors self-start sm:self-auto"
        >
          Evaluate Asset in Assistant →
        </Link>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-critical-50 border border-critical-200 text-critical-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Multi-Filter and Search Bar */}
      <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search assets by name, ID (e.g. AST-0065), product, or market..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-intelligence"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
            {/* Platform Filter */}
            <select
              value={platform}
              onChange={(e) => {
                setPlatform(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 font-medium bg-white focus:outline-none focus:ring-2 focus:ring-intelligence"
            >
              <option value="">All Platforms</option>
              <option value="Power BI">Power BI (266)</option>
              <option value="Tableau">Tableau (94)</option>
            </select>

            {/* Endorsement Filter */}
            <select
              value={endorsement}
              onChange={(e) => {
                setEndorsement(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 font-medium bg-white focus:outline-none focus:ring-2 focus:ring-intelligence"
            >
              <option value="">All Endorsements</option>
              <option value="certified">Certified</option>
              <option value="promoted">Promoted</option>
              <option value="none">Self-Service (None)</option>
            </select>

            {/* Lifecycle Status Filter */}
            <select
              value={lifecycleStatus}
              onChange={(e) => {
                setLifecycleStatus(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 font-medium bg-white focus:outline-none focus:ring-2 focus:ring-intelligence"
            >
              <option value="">All Lifecycles</option>
              <option value="active">Active</option>
              <option value="legacy">Legacy</option>
              <option value="candidate_retire">Candidate Retire</option>
            </select>

            {/* Product Family Filter */}
            <select
              value={productFilter}
              onChange={(e) => {
                setProductFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 font-medium bg-white focus:outline-none focus:ring-2 focus:ring-intelligence"
            >
              <option value="">All Products</option>
              {uniqueProducts.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Counter Summary */}
        <div className="flex items-center justify-between text-xs text-gray-500 pt-1 border-t border-gray-100">
          <span>
            Showing <strong className="text-gray-900">{totalFiltered}</strong> matching assets
            {platform && ` on ${platform}`}
            {endorsement && ` (${endorsement})`}
          </span>
          <span className="font-mono text-[11px]">
            Page {page} of {totalPages}
          </span>
        </div>
      </div>

      {/* Assets Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-gray-500 flex flex-col items-center justify-center gap-2">
            <RefreshCw className="w-5 h-5 animate-spin text-intelligence" />
            <span>Loading enterprise analytics portfolio...</span>
          </div>
        ) : paginatedAssets.length === 0 ? (
          <div className="p-12 text-center text-sm text-gray-500">
            No analytics assets found matching the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-gray-600 font-bold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Asset ID & Name</th>
                  <th className="py-3 px-4">Platform</th>
                  <th className="py-3 px-4">Product & Market</th>
                  <th className="py-3 px-4">Owner</th>
                  <th className="py-3 px-4">Endorsement</th>
                  <th className="py-3 px-4">Lifecycle</th>
                  <th className="py-3 px-4 text-right">Audience</th>
                  <th className="py-3 px-4 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {paginatedAssets.map((asset) => (
                  <tr key={asset.asset_id} className="hover:bg-gray-50/80 transition-colors group">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/assets/${asset.asset_id}`}
                          className="font-mono font-bold text-intelligence hover:underline"
                        >
                          {asset.asset_id}
                        </Link>
                      </div>
                      <div className="font-semibold text-gray-900 text-xs mt-0.5 line-clamp-1">
                        {asset.asset_name}
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-medium text-[11px] ${
                          asset.platform === "Power BI"
                            ? "bg-amber-50 text-amber-800 border border-amber-200/60"
                            : "bg-blue-50 text-blue-800 border border-blue-200/60"
                        }`}
                      >
                        {asset.platform}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <div className="font-medium text-gray-800">{asset.product_scope || "—"}</div>
                      <div className="text-[10px] text-gray-500 font-mono">Market: {asset.market_scope || "Global"}</div>
                    </td>

                    <td className="py-3 px-4 font-mono text-[11px]">
                      {asset.owner_id ? (
                        <span className="text-gray-700">{asset.owner_id}</span>
                      ) : (
                        <span className="text-critical font-bold bg-red-50 px-1.5 py-0.5 rounded">Unowned</span>
                      )}
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                          asset.endorsement === "certified"
                            ? "bg-emerald-100 text-trust"
                            : asset.endorsement === "promoted"
                            ? "bg-blue-100 text-intelligence"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {asset.endorsement || "none"}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                          asset.lifecycle_status === "active"
                            ? "bg-emerald-50 text-emerald-800"
                            : asset.lifecycle_status === "candidate_retire"
                            ? "bg-red-50 text-critical font-bold"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {asset.lifecycle_status}
                      </span>
                    </td>

                    <td className="py-3 px-4 text-right font-mono text-gray-700">
                      {asset.estimated_audience ? asset.estimated_audience.toLocaleString() : "—"}
                    </td>

                    <td className="py-3 px-4 text-center">
                      <Link
                        href={`/assets/${asset.asset_id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-intelligence hover:text-intelligence-600 transition-colors"
                      >
                        Inspect <ExternalLink className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="p-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between text-xs text-gray-600">
            <div>
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, totalFiltered)} of {totalFiltered} assets
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2.5 py-1 rounded bg-white border border-gray-300 disabled:opacity-40 font-medium hover:bg-gray-100"
              >
                Previous
              </button>
              <span className="px-2 font-mono">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-2.5 py-1 rounded bg-white border border-gray-300 disabled:opacity-40 font-medium hover:bg-gray-100"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
