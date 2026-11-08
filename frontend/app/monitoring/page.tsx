'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { MonitoringSummary, MonitoringJob } from '@/lib/types';
import { formatMs, formatPercent } from '@/lib/format';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Play,
  RotateCcw,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  Filter,
  Layers,
  Database,
  Bell,
  RefreshCw,
  Search,
} from 'lucide-react';

const SCAN_TYPES = [
  { id: 'FULL_CONTINUOUS_SCAN', label: 'Full Continuous Scan (All Subsystems)' },
  { id: 'GOVERNANCE_REEVAL', label: 'Governance Rule Re-Evaluation (8 Rules)' },
  { id: 'CATALOG_SYNC', label: 'External BI Catalogue Synchronization' },
  { id: 'DUPLICATE_DETECTION', label: 'Cross-Platform Duplicate Detection' },
  { id: 'OWNERSHIP_AUDIT', label: 'Accountable Ownership Verification' },
  { id: 'SEMANTIC_READINESS', label: 'Semantic Model Health & AI Readiness' },
];

export default function MonitoringPage() {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [jobs, setJobs] = useState<MonitoringJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [selectedScanType, setSelectedScanType] = useState('FULL_CONTINUOUS_SCAN');
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('ALL');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [sumData, jobsData] = await Promise.all([
        api.getMonitoringSummary(),
        api.getMonitoringJobs(),
      ]);
      setSummary(sumData);
      setJobs(jobsData);
    } catch (err: any) {
      console.error('Failed to load monitoring data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerJob() {
    try {
      setTriggering(true);
      await api.triggerMonitoringJob(selectedScanType, 'USER_CONSOLE');
      await loadData();
    } catch (err: any) {
      alert(`Monitoring job failed: ${err.message}`);
    } finally {
      setTriggering(false);
    }
  }

  const filteredJobs = jobs.filter((j) => {
    if (statusFilter === 'ALL') return true;
    return j.status === statusFilter;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'SUCCESS':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Success
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
            <RefreshCw className="w-3.5 h-3.5 text-blue-600 animate-spin" /> Running
          </span>
        );
      case 'PARTIAL_SUCCESS':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Partial
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">
            <XCircle className="w-3.5 h-3.5 text-rose-600" /> Failed
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700 font-mono">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Continuous Analytics Governance & Monitoring
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Automated scheduled re-evaluations, catalog synchronization, defect change detection, and alert synchronization.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/alerts"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
          >
            <Bell className="w-3.5 h-3.5 text-rose-600" />
            Alert Centre
          </Link>
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Telemetry Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Monitoring Cadence</span>
          <div className="flex items-center justify-between">
            <span className="text-xl font-bold text-gray-900">Automated</span>
          </div>
          <span className="text-[11px] text-gray-400">Scheduled re-evaluations</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Total Monitoring Executions</span>
          <div className="flex items-center justify-between">
            <span className="text-xl font-bold text-gray-900 font-mono">
              {summary?.total_jobs_executed ?? 0}
            </span>
            <Activity className="w-4 h-4 text-intelligence" />
          </div>
          <span className="text-[11px] text-emerald-600 font-medium">
            {summary?.successful_jobs ?? 0} Successful
          </span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Active Critical Alerts</span>
          <div className="flex items-center justify-between">
            <span className="text-xl font-bold text-rose-600 font-mono">
              {summary?.alerts.unresolved_critical ?? 0}
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
              URGENT
            </span>
          </div>
          <span className="text-[11px] text-gray-500">
            {summary?.alerts.unresolved_high ?? 0} High Priority
          </span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Resolved & Acknowledged</span>
          <div className="flex items-center justify-between">
            <span className="text-xl font-bold text-emerald-700 font-mono">
              {summary?.alerts.resolved ?? 0}
            </span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <span className="text-[11px] text-slate-500">
            {summary?.alerts.acknowledged ?? 0} Acknowledged with Rationale
          </span>
        </div>
      </div>

      {/* Manual Execution Trigger Bar */}
      <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full md:w-auto">
          <div className="w-9 h-9 rounded-lg bg-intelligence/10 text-intelligence flex items-center justify-center shrink-0">
            <Play className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-bold text-gray-900">Trigger On-Demand Monitoring Job</div>
            <div className="text-[11px] text-gray-500">Run an authoritative scan with instant change detection and alert update.</div>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto">
          <select
            value={selectedScanType}
            onChange={(e) => setSelectedScanType(e.target.value)}
            className="flex-1 md:w-72 px-3 py-2 rounded-lg border border-gray-300 text-xs bg-white text-gray-800 focus:outline-none focus:ring-1 focus:ring-intelligence"
          >
            {SCAN_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          <button
            onClick={handleTriggerJob}
            disabled={triggering}
            className="px-4 py-2 rounded-lg bg-midnight-900 hover:bg-midnight-800 text-white text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 flex items-center gap-2 shrink-0"
          >
            <Play className={`w-3.5 h-3.5 ${triggering ? 'animate-spin' : ''}`} />
            {triggering ? 'Running...' : 'Execute Now'}
          </button>
        </div>
      </div>

      {/* Job Execution History */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-2">
            <Clock className="w-4 h-4 text-intelligence" />
            Monitoring Execution History ({filteredJobs.length} Runs)
          </h2>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">Filter Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2 py-1 border border-gray-300 rounded text-xs bg-white"
            >
              <option value="ALL">All Statuses</option>
              <option value="SUCCESS">Success</option>
              <option value="PARTIAL_SUCCESS">Partial</option>
              <option value="FAILED">Failed</option>
              <option value="RUNNING">Running</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-gray-50/75 border-b border-gray-200 text-gray-500 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-4 py-3">Job ID</th>
                <th className="px-4 py-3">Job Type</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3 text-right">Duration</th>
                <th className="px-4 py-3 text-right">Processed</th>
                <th className="px-4 py-3 text-right">Findings</th>
                <th className="px-4 py-3 text-center">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-medium">
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                    No monitoring job executions found matching criteria.
                  </td>
                </tr>
              ) : (
                filteredJobs.map((j) => {
                  const isExpanded = expandedJobId === j.job_id;
                  let parsedDetails = null;
                  try {
                    if (j.details_json) parsedDetails = JSON.parse(j.details_json);
                  } catch {}

                  return (
                    <tr key={j.job_id} className="hover:bg-gray-50/60 transition-colors">
                      <td className="px-4 py-3 font-mono font-bold text-gray-900">{j.job_id}</td>
                      <td className="px-4 py-3 text-gray-700 font-mono text-[11px]">{j.job_type}</td>
                      <td className="px-4 py-3">{getStatusBadge(j.status)}</td>
                      <td className="px-4 py-3 font-mono text-gray-500">
                        {j.started_at ? new Date(j.started_at).toLocaleTimeString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-gray-700">{formatMs(j.duration_ms)}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-900 font-bold">{j.records_processed}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        <span className="text-rose-600 font-bold">+{j.findings_generated}</span>
                        {j.findings_resolved > 0 && (
                          <span className="text-emerald-600 ml-1">(-{j.findings_resolved})</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => setExpandedJobId(isExpanded ? null : j.job_id)}
                          className="px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-100 text-[11px] text-gray-600"
                        >
                          {isExpanded ? 'Hide' : 'Inspect'}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

