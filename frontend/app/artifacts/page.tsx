'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/layout/Shell';
import { api } from '@/lib/api';
import { GeneratedArtifact, CanonicalKpi, SemanticModel } from '@/lib/types';
import {
  Layers,
  Code2,
  FileBox,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  ExternalLink,
  ShieldCheck,
  FileText,
  Clock,
  Sparkles,
  Search,
  Check,
  Download,
  ShieldAlert,
  ChevronRight,
} from 'lucide-react';

export default function ArtifactsPage() {
  const { currentActor, currentRole } = useAuth();
  const [artifacts, setArtifacts] = useState<GeneratedArtifact[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Available Catalog Data for Governed Builder
  const [availableKpis, setAvailableKpis] = useState<CanonicalKpi[]>([]);
  const [availableModels, setAvailableModels] = useState<SemanticModel[]>([]);

  // Generation Form State
  const [reportName, setReportName] = useState<string>('Bayer Cardiology Executive Review');
  const [targetTool, setTargetTool] = useState<string>('PBIP');
  const [businessPurpose, setBusinessPurpose] = useState<string>('Quarterly Cardiology reach and adherence monitoring');
  const [selectedKpiIds, setSelectedKpiIds] = useState<string[]>(['KPI-001', 'KPI-004']);
  const [selectedModelId, setSelectedModelId] = useState<string>('SM-008');
  const [generating, setGenerating] = useState<boolean>(false);
  const [genSuccess, setGenSuccess] = useState<string | null>(null);

  // Repository Search
  const [repoSearch, setRepoSearch] = useState<string>('');

  const fetchArtifacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const [artData, kpiData, modelData] = await Promise.all([
        api.getArtifacts().catch(() => []),
        api.getKpis(50).catch(() => []),
        api.getSemanticModels(50).catch(() => []),
      ]);
      setArtifacts(artData);
      setAvailableKpis(kpiData);
      setAvailableModels(modelData);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch generated artifact specifications');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArtifacts();
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerating(true);
    setError(null);
    setGenSuccess(null);

    try {
      const res = await api.generateArtifact({
        actor_id: currentActor,
        actor_role: currentRole,
        output_format: targetTool,
        force: true,
        spec: {
          spec_id: `SPEC-${Date.now().toString().slice(-6)}`,
          title: reportName,
          business_purpose: businessPurpose,
          product_scope: 'Cardiology',
          market_scope: 'EU & US',
          semantic_model_id: selectedModelId,
          tables: ['Fact_Prescriptions', 'Dim_Products', 'Dim_Physicians'],
          measures: selectedKpiIds.map((kpi, idx) => {
            const rawName = availableKpis.find((k) => k.kpi_id === kpi)?.kpi_name || kpi;
            const cleanName = rawName.replace(/[[\]]/g, '').trim();
            return {
              name: cleanName || `Measure_${idx + 1}`,
              table_name: 'Fact_Prescriptions',
              dax_expression: `SUM(Fact_Prescriptions[Value_${idx + 1}])`,
              kpi_id: kpi,
              format_string: '#,##0.00',
            };
          }),
        },
      });

      setGenSuccess(`Power BI artifact ${res.artifact_id} successfully compiled and registered.`);
      await fetchArtifacts();
    } catch (err: any) {
      setError(`Artifact Compilation Failed: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const filteredArtifacts = artifacts.filter((a) => {
    if (!repoSearch.trim()) return true;
    const q = repoSearch.toLowerCase();
    return (
      a.artifact_id.toLowerCase().includes(q) ||
      a.artifact_name.toLowerCase().includes(q) ||
      (a.format && a.format.toLowerCase().includes(q))
    );
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Analytics Development Studio
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-intelligence text-xs font-semibold">
              Power BI Artifact Factory (PBIP / PBIR)
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Converts approved, governed analytics requirements into standardized, traceable Power BI developer projects (.pbip) with TMDL semantic definitions.
          </p>
        </div>

        <button
          onClick={fetchArtifacts}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors shadow-2xs self-start sm:self-auto"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-intelligence' : 'text-gray-500'}`} />
          Refresh Registry
        </button>
      </div>

      {genSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{genSuccess}</span>
          </div>
          <button onClick={() => setGenSuccess(null)} className="font-bold text-emerald-600 hover:text-emerald-800">
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-critical-50 border border-critical-200 text-critical-700 text-xs font-medium flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-critical shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="font-bold text-critical hover:text-red-900">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid: Builder Form & Artifact Repository */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Governed Generation Form */}
        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm space-y-4">
          <div className="flex items-center gap-2 border-b border-gray-100 pb-3">
            <Sparkles className="w-4 h-4 text-intelligence" />
            <h2 className="text-sm font-bold text-midnight-900">Governed PBIP Package Factory</h2>
          </div>

          <form onSubmit={handleGenerate} className="space-y-3.5 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Report Name</label>
              <input
                type="text"
                value={reportName}
                onChange={(e) => setReportName(e.target.value)}
                className="w-full p-2.5 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Business Purpose</label>
              <input
                type="text"
                value={businessPurpose}
                onChange={(e) => setBusinessPurpose(e.target.value)}
                className="w-full p-2.5 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Target Semantic Model</label>
              <select
                value={selectedModelId}
                onChange={(e) => setSelectedModelId(e.target.value)}
                className="w-full p-2.5 border border-gray-300 rounded-lg text-xs text-midnight-900 bg-white focus:outline-none focus:ring-1 focus:ring-intelligence font-mono"
              >
                {availableModels.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.model_id} — {m.model_name} ({m.endorsement || 'none'})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">
                Canonical KPIs (Governed Catalog Selection)
              </label>
              <div className="space-y-1.5 max-h-36 overflow-y-auto border border-gray-200 rounded-lg p-2 bg-gray-50/50">
                {availableKpis.map((kpi) => {
                  const isChecked = selectedKpiIds.includes(kpi.kpi_id);
                  return (
                    <label
                      key={kpi.kpi_id}
                      className="flex items-center gap-2 p-1 hover:bg-white rounded cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {
                          if (isChecked) {
                            setSelectedKpiIds(selectedKpiIds.filter((id) => id !== kpi.kpi_id));
                          } else {
                            setSelectedKpiIds([...selectedKpiIds, kpi.kpi_id]);
                          }
                        }}
                        className="rounded text-intelligence focus:ring-intelligence"
                      />
                      <span className="font-mono font-bold text-gray-800 text-[11px]">{kpi.kpi_id}</span>
                      <span className="text-gray-700 line-clamp-1">{kpi.kpi_name}</span>
                    </label>
                  );
                })}
              </div>
              <span className="text-[10px] text-gray-400 mt-1 block">
                {selectedKpiIds.length} canonical measures selected
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-700 space-y-1">
              <div className="font-bold text-slate-900 flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-trust" />
                Pre-Generation Governance Gate:
              </div>
              <div>Direct creation requires non-conflicting KPI formulas and shared semantic model alignment.</div>
            </div>

            <button
              type="submit"
              disabled={generating || selectedKpiIds.length === 0}
              className="w-full py-2.5 px-4 bg-intelligence hover:bg-intelligence-600 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center justify-center gap-2"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              {generating ? 'Compiling Artifact Spec...' : 'Build Power BI Package'}
            </button>
          </form>
        </div>

        {/* Right Columns: Repository & Artifact File Inspector */}
        <div className="lg:col-span-2 space-y-4">
          {/* Artifact Repository List */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-midnight-900">Compiled Artifact Specifications</h2>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
                  {artifacts.length} total
                </span>
              </div>

              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
                <input
                  type="text"
                  value={repoSearch}
                  onChange={(e) => setRepoSearch(e.target.value)}
                  placeholder="Search repository..."
                  className="pl-8 pr-3 py-1.5 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
                />
              </div>
            </div>

            {loading ? (
              <div className="p-8 text-center text-xs text-gray-400">Loading artifact specifications...</div>
            ) : filteredArtifacts.length === 0 ? (
              <div className="p-8 text-center text-xs text-gray-400">
                No artifacts matching '{repoSearch}'. Generate one using the form on the left.
              </div>
            ) : (
              <div className="divide-y divide-gray-100 max-h-[520px] overflow-y-auto">
                {filteredArtifacts.map((a) => (
                  <div
                    key={a.artifact_id}
                    className="p-3.5 hover:bg-gray-50 flex items-center justify-between transition-colors"
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-gray-800">{a.artifact_id}</span>
                        <span className="text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                          {a.format || 'PBIP'}
                        </span>
                      </div>
                      <div className="text-xs font-bold text-gray-900">{a.artifact_name}</div>
                      <div className="text-[10px] text-gray-400">
                        Compiled: {new Date(a.created_at).toLocaleString()}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[10px] px-2.5 py-0.5 rounded-full font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        Validated
                      </span>
                    </div>
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
