'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/layout/Shell';
import { api } from '@/lib/api';
import { GovernanceAlert, AlertsSummary } from '@/lib/types';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ShieldAlert,
  Search,
  Filter,
  ArrowRight,
  ExternalLink,
  RotateCcw,
  ShieldCheck,
  UserCheck,
  Check,
  X,
  FileText,
} from 'lucide-react';

export default function AlertsPage() {
  const { currentActor, currentRole } = useAuth();
  const [alerts, setAlerts] = useState<GovernanceAlert[]>([]);
  const [summary, setSummary] = useState<AlertsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('NEW');
  const [searchQuery, setSearchQuery] = useState('');

  // Acknowledge Modal State
  const [activeAlert, setActiveAlert] = useState<GovernanceAlert | null>(null);
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  useEffect(() => {
    loadAlertsData();
  }, [severityFilter, statusFilter]);

  async function loadAlertsData() {
    try {
      setLoading(true);
      setError(null);
      const sev = severityFilter === 'ALL' ? undefined : severityFilter;
      const st = statusFilter === 'ALL' ? undefined : statusFilter;
      const [alertsData, sumData] = await Promise.all([
        api.getAlerts(sev, st, undefined, searchQuery || undefined),
        api.getAlertsSummary(),
      ]);
      setAlerts(alertsData);
      setSummary(sumData);
    } catch (err: any) {
      setError(err.message || 'Failed to load governance alerts.');
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    loadAlertsData();
  }

  async function handleAcknowledgeSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!activeAlert) return;
    if (rationale.trim().length < 5) {
      setModalError('Rationale must be at least 5 characters long.');
      return;
    }

    try {
      setSubmitting(true);
      setModalError(null);
      await api.acknowledgeAlert(activeAlert.alert_id, currentActor, currentRole, rationale.trim());
      setActiveAlert(null);
      setRationale('');
      await loadAlertsData();
    } catch (err: any) {
      setModalError(err.message || 'Failed to acknowledge alert.');
    } finally {
      setSubmitting(false);
    }
  }

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200 uppercase">
            <XCircle className="w-3.5 h-3.5 text-rose-600" /> Critical
          </span>
        );
      case 'high':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200 uppercase">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> High
          </span>
        );
      case 'medium':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-800 border border-yellow-200 uppercase">
            Medium
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200 uppercase">
            Low
          </span>
        );
    }
  };

  const getStatusBadge = (st: string) => {
    switch (st) {
      case 'NEW':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
            NEW / UNRESOLVED
          </span>
        );
      case 'ACKNOWLEDGED':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-700 border border-slate-300">
            ACKNOWLEDGED
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            RESOLVED
          </span>
        );
      default:
        return <span className="font-mono text-xs">{st}</span>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Governance Alert Centre
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-800 text-xs font-semibold flex items-center gap-1">
              <Bell className="w-3.5 h-3.5" /> Actionable Queue
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Operational alerts generated from deterministic governance checks. Acknowledging alerts records awareness without clearing violations.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/governance"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-intelligence" />
            Governance Console
          </Link>
          <button
            onClick={loadAlertsData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Critical Alerts</span>
          <div className="text-2xl font-bold text-rose-600 font-mono">
            {summary?.by_severity.critical ?? 0}
          </div>
          <span className="text-[11px] text-gray-400">High Blast Radius</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">High Priority</span>
          <div className="text-2xl font-bold text-amber-600 font-mono">
            {summary?.by_severity.high ?? 0}
          </div>
          <span className="text-[11px] text-gray-400">Policy Violations</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Acknowledged</span>
          <div className="text-2xl font-bold text-slate-700 font-mono">
            {summary?.by_status.ACKNOWLEDGED ?? 0}
          </div>
          <span className="text-[11px] text-slate-500">Documented Awareness</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-1">
          <span className="text-xs text-gray-500 font-medium">Remediated & Resolved</span>
          <div className="text-2xl font-bold text-emerald-600 font-mono">
            {summary?.by_status.RESOLVED ?? 0}
          </div>
          <span className="text-[11px] text-emerald-600">Fixed at Source</span>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Filter className="w-3.5 h-3.5" /> Severity:
          </div>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs bg-white text-gray-700"
          >
            <option value="ALL">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <div className="flex items-center gap-1.5 text-xs text-gray-500 ml-2">
            Status:
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs bg-white text-gray-700"
          >
            <option value="ALL">All Statuses</option>
            <option value="NEW">New (Unresolved)</option>
            <option value="ACKNOWLEDGED">Acknowledged</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </div>

        <form onSubmit={handleSearchSubmit} className="relative w-full sm:w-72">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search asset, rule, or title..."
            className="w-full pl-8 pr-3 py-1.5 border border-gray-300 rounded-lg text-xs text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence"
          />
          <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2.5" />
        </form>
      </div>

      {/* Alerts Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-gray-50/75 border-b border-gray-200 text-gray-500 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Target Entity</th>
                <th className="px-4 py-3">Governance Rule</th>
                <th className="px-4 py-3">Violation Title & Explanation</th>
                <th className="px-4 py-3">Recommended Remediation</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-medium">
              {loading && alerts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    Loading governance alerts...
                  </td>
                </tr>
              ) : alerts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    No governance alerts found matching the selected filters.
                  </td>
                </tr>
              ) : (
                alerts.map((a) => {
                  const isAsset = a.target_entity_type === 'asset';

                  return (
                    <tr key={a.alert_id} className="hover:bg-gray-50/60 transition-colors">
                      <td className="px-4 py-3.5 align-top">{getSeverityBadge(a.severity)}</td>
                      <td className="px-4 py-3.5 align-top">
                        {isAsset ? (
                          <Link
                            href={`/assets/${a.target_entity_id}`}
                            className="font-mono font-bold text-intelligence hover:underline inline-flex items-center gap-1"
                          >
                            {a.target_entity_id}
                            <ExternalLink className="w-3 h-3 text-gray-400" />
                          </Link>
                        ) : (
                          <span className="font-mono font-bold text-gray-900">{a.target_entity_id}</span>
                        )}
                        <span className="block text-[10px] text-gray-400 uppercase tracking-wider">
                          {a.target_entity_type}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 align-top font-mono font-semibold text-gray-700">
                        {a.rule_id}
                      </td>
                      <td className="px-4 py-3.5 align-top max-w-xs space-y-1">
                        <div className="font-bold text-gray-900 leading-snug">{a.title}</div>
                        <p className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed">{a.explanation}</p>
                      </td>
                      <td className="px-4 py-3.5 align-top max-w-xs text-[11px] text-gray-700 leading-relaxed">
                        {a.recommended_action}
                      </td>
                      <td className="px-4 py-3.5 align-top">
                        {getStatusBadge(a.status)}
                        {a.acknowledged_by && (
                          <span className="block text-[10px] text-gray-400 font-mono mt-0.5">
                            By {a.acknowledged_by}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3.5 align-top text-center">
                        {a.status === 'NEW' ? (
                          <button
                            onClick={() => {
                              setActiveAlert(a);
                              setRationale('');
                              setModalError(null);
                            }}
                            className="px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 text-white text-[11px] font-semibold transition-colors shadow-sm"
                          >
                            Acknowledge
                          </button>
                        ) : a.status === 'ACKNOWLEDGED' ? (
                          <span className="text-[11px] text-gray-400 font-mono">Acknowledged</span>
                        ) : (
                          <span className="text-[11px] text-emerald-600 font-semibold">Resolved</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Acknowledge Modal */}
      {activeAlert && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-gray-200 overflow-hidden">
            <div className="p-5 border-b border-gray-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-rose-600" />
                <h3 className="font-bold text-gray-900 text-sm">
                  Acknowledge Governance Alert ({activeAlert.alert_id})
                </h3>
              </div>
              <button
                onClick={() => setActiveAlert(null)}
                className="text-gray-400 hover:text-gray-600 p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAcknowledgeSubmit} className="p-5 space-y-4 text-xs">
              {modalError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800">
                  {modalError}
                </div>
              )}

              <div className="p-3 rounded-lg bg-amber-50/70 border border-amber-200 text-amber-900 space-y-1">
                <div className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  Governance Non-Negotiable Invariant
                </div>
                <p className="text-[11px] leading-relaxed">
                  Acknowledging this alert documents operational awareness and records your accountability in the
                  audit trail. It does <strong>NOT</strong> silently clear or resolve the underlying{' '}
                  <strong>{activeAlert.rule_id}</strong> violation in BIOS. The finding remains active until remediated.
                </p>
              </div>

              <div className="space-y-1">
                <span className="text-gray-500">Target Entity:</span>
                <div className="font-mono font-bold text-gray-900">
                  {activeAlert.target_entity_id} ({activeAlert.target_entity_type})
                </div>
              </div>

              <div className="space-y-1">
                <span className="text-gray-500">Violation Title:</span>
                <div className="font-semibold text-gray-800">{activeAlert.title}</div>
              </div>

              <div className="space-y-1">
                <label className="font-bold text-gray-700 block">
                  Mandatory Business Rationale & Remediation Plan (Min. 5 characters):
                </label>
                <textarea
                  rows={3}
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  placeholder="State why this alert is acknowledged and when remediation will take place..."
                  className="w-full p-2.5 rounded-lg border border-gray-300 text-xs focus:ring-1 focus:ring-intelligence focus:outline-none"
                  required
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setActiveAlert(null)}
                  className="px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50 font-medium text-gray-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || rationale.trim().length < 5}
                  className="px-4 py-1.5 rounded-lg bg-midnight-900 hover:bg-midnight-800 text-white font-semibold transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Submitting...' : 'Confirm Acknowledgement'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

