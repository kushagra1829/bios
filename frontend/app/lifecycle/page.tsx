'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { MigrationCandidate, MigrationSummary } from '@/lib/types';
import { formatPercent } from '@/lib/format';
import {
  Layers,
  ArrowRightCircle,
  Clock,
  Sparkles,
  Filter,
  Search,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ExternalLink,
  ShieldAlert,
  FileSpreadsheet,
  CheckSquare,
  ArrowRight,
  TrendingDown,
  Info,
} from 'lucide-react';

export default function LifecyclePage() {
  const [summary, setSummary] = useState<MigrationSummary | null>(null);
  const [candidates, setCandidates] = useState<MigrationCandidate[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [actionFilter, setActionFilter] = useState<string>('ALL');
  const [complexityFilter, setComplexityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const aParam = actionFilter === 'ALL' ? undefined : actionFilter;
      const cParam = complexityFilter === 'ALL' ? undefined : complexityFilter;
      const [sumData, candData] = await Promise.all([
        api.getMigrationSummary().catch(() => null),
        api.getMigrationCandidates(aParam, cParam).catch(() => []),
      ]);
      setSummary(sumData);
      setCandidates(candData);
    } catch (err: any) {
      setError(err.message || 'Failed to load migration intelligence');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [actionFilter, complexityFilter]);

  const filteredCandidates = candidates.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.source_asset_id.toLowerCase().includes(q) ||
      (c.source_asset_name && c.source_asset_name.toLowerCase().includes(q)) ||
      (c.rationalization_rationale && c.rationalization_rationale.toLowerCase().includes(q)) ||
      (c.candidate_target_model_id && c.candidate_target_model_id.toLowerCase().includes(q))
    );
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Analytics Lifecycle & Estate Rationalization
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-purple-100 text-purple-800 text-xs font-semibold">
              94 Tableau Legacy Assets
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Governed migration and retirement intelligence for 94 Tableau legacy assets based on usage, health, and duplicate clustering.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/approvals"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors shadow-2xs"
          >
            <CheckSquare className="w-3.5 h-3.5 text-trust" />
            Adjudicate Lifecycle Approvals
          </Link>
          <button
            onClick={fetchData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors shadow-2xs"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-intelligence' : 'text-gray-500'}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-critical-50 border border-critical-200 text-critical-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 1. Executive Summary Telemetry */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Tableau Legacy</span>
          <div className="text-2xl font-extrabold text-midnight-900">
            {summary?.total_tableau_assets ?? 94}
          </div>
          <div className="text-[11px] text-gray-400">Total assets in scope</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-intelligence uppercase tracking-wider">Consolidate Before</span>
          <div className="text-2xl font-extrabold text-intelligence">
            {summary?.consolidate_count ?? 30}
          </div>
          <div className="text-[11px] text-blue-600">Eliminates report sprawl</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-critical uppercase tracking-wider">Retire Instead</span>
          <div className="text-2xl font-extrabold text-critical">
            {summary?.retire_instead_count ?? 16}
          </div>
          <div className="text-[11px] text-red-500">Zero-view dormant waste</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-trust uppercase tracking-wider">Direct Migrate</span>
          <div className="text-2xl font-extrabold text-trust">
            {summary?.direct_migrate_count ?? 13}
          </div>
          <div className="text-[11px] text-gray-500">Target Power BI model identified</div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Effort Reduction</span>
          <div className="text-2xl font-extrabold text-purple-700 flex items-center gap-1">
            <TrendingDown className="w-5 h-5 text-purple-600" />
            {summary?.estimated_effort_reduction_pct ?? 48.9}%
          </div>
          <div className="text-[11px] text-purple-600">Saved migration expense</div>
        </div>
      </div>

      {/* 2. Filter Bar */}
      <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search candidates by ID, name, target model, or rationale..."
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 bg-white font-medium focus:outline-none focus:ring-1 focus:ring-intelligence"
          >
            <option value="ALL">All Actions</option>
            <option value="CONSOLIDATE_BEFORE_MIGRATION">Consolidate Before Migration (30)</option>
            <option value="FIX_BEFORE_MIGRATION">Fix Before Migration (20)</option>
            <option value="RETIRE_INSTEAD_OF_MIGRATE">Retire Instead of Migrate (16)</option>
            <option value="HOLD_FOR_REVIEW">Hold for Review (15)</option>
            <option value="MIGRATE">Direct Migrate (13)</option>
          </select>

          <select
            value={complexityFilter}
            onChange={(e) => setComplexityFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-xs text-midnight-900 bg-white font-medium focus:outline-none focus:ring-1 focus:ring-intelligence"
          >
            <option value="ALL">All Complexities</option>
            <option value="low">Low Complexity</option>
            <option value="medium">Medium Complexity</option>
            <option value="high">High Complexity</option>
          </select>
        </div>
      </div>

      {/* 3. Candidate Cards List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-gray-500 font-medium">
          <span>Displaying {filteredCandidates.length} rationalization candidates</span>
          <span>Governed by RULE-006 (Do Not Migrate Waste)</span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-xs text-gray-400 bg-white rounded-xl border border-gray-200">
            <RotateCcw className="w-5 h-5 animate-spin mx-auto text-intelligence mb-2" />
            Loading migration backlog...
          </div>
        ) : filteredCandidates.length === 0 ? (
          <div className="p-12 text-center text-xs text-gray-400 bg-white rounded-xl border border-gray-200">
            No migration candidates matching the specified criteria.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredCandidates.map((c) => (
              <div
                key={c.migration_id}
                className="p-5 bg-white rounded-xl border border-gray-200 shadow-sm space-y-3 hover:border-gray-300 transition-all text-xs"
              >
                {/* Top Row: Asset ID, Action Badge, Complexity */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/assets/${c.source_asset_id}`}
                      className="font-mono font-bold text-intelligence hover:underline"
                    >
                      {c.source_asset_id}
                    </Link>
                    <span className="text-gray-400">·</span>
                    <span className="font-semibold text-gray-900">{c.source_asset_name || 'Tableau Workbook'}</span>
                  </div>

                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      c.recommended_action === 'CONSOLIDATE_BEFORE_MIGRATION'
                        ? 'bg-blue-100 text-intelligence'
                        : c.recommended_action === 'RETIRE_INSTEAD_OF_MIGRATE'
                        ? 'bg-red-100 text-critical'
                        : c.recommended_action === 'MIGRATE'
                        ? 'bg-emerald-100 text-trust'
                        : c.recommended_action === 'FIX_BEFORE_MIGRATION'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-purple-100 text-purple-800'
                    }`}
                  >
                    {c.recommended_action.replace(/_/g, ' ')}
                  </span>
                </div>

                {/* Rationale */}
                <p className="text-gray-700 leading-relaxed font-sans bg-gray-50 p-2.5 rounded-lg border border-gray-100">
                  {c.rationalization_rationale}
                </p>

                {/* Technical Metadata Row */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] text-gray-500 font-mono pt-1 border-t border-gray-100">
                  <div>
                    <span>Complexity: </span>
                    <strong className="text-gray-800 uppercase">{c.technical_complexity}</strong>
                  </div>

                  <div>
                    <span>Target Model: </span>
                    <strong className="text-intelligence">{c.candidate_target_model_id || 'None'}</strong>
                  </div>

                  <div>
                    <span>Dependencies: </span>
                    <strong className="text-gray-800">{c.downstream_dependency_count} downstream</strong>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center justify-between pt-1 text-xs">
                  <Link
                    href={`/assets/${c.source_asset_id}`}
                    className="text-gray-500 hover:text-midnight-900 font-medium inline-flex items-center gap-1"
                  >
                    Inspect Asset <ExternalLink className="w-3 h-3" />
                  </Link>

                  <Link
                    href="/approvals"
                    className="text-intelligence font-bold hover:underline inline-flex items-center gap-1"
                  >
                    Review in Approvals →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
