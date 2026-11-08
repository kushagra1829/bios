'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/layout/Shell';
import { api } from '@/lib/api';
import { IntegrationStatus, ConnectionTestResult, SyncResult } from '@/lib/types';
import {
  PlugZap,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  Layers,
  Database,
  FileSpreadsheet,
  KeyRound,
  ExternalLink,
  ShieldCheck,
  Server,
  Activity,
  ArrowRight,
  Info,
  Lock,
} from 'lucide-react';

export default function IntegrationsPage() {
  const { currentActor, currentRole } = useAuth();
  const isAdmin = currentRole === 'Platform Administrator';

  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [testingId, setTestingId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; result: ConnectionTestResult } | null>(null);
  const [syncResult, setSyncResult] = useState<{ id: string; result: SyncResult } | null>(null);

  useEffect(() => {
    loadIntegrations();
  }, []);

  async function loadIntegrations() {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getIntegrations();
      setIntegrations(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load BI platform integration status.');
    } finally {
      setLoading(false);
    }
  }

  async function handleTestConnection(connectorId: string) {
    try {
      setTestingId(connectorId);
      setTestResult(null);
      const res = await api.testIntegration(connectorId);
      setTestResult({ id: connectorId, result: res });
      loadIntegrations();
    } catch (err: any) {
      setTestResult({
        id: connectorId,
        result: { status: 'AUTH_FAILED', message: err.message || 'Connection test failed.' },
      });
    } finally {
      setTestingId(null);
    }
  }

  async function handleSync(connectorId: string) {
    try {
      setSyncingId(connectorId);
      setSyncResult(null);
      const res = await api.syncIntegration(connectorId);
      setSyncResult({ id: connectorId, result: res });
      loadIntegrations();
    } catch (err: any) {
      setSyncResult({
        id: connectorId,
        result: {
          connector_id: connectorId,
          status: 'SYNC_FAILED',
          imported_workspaces: 0,
          imported_reports: 0,
          imported_models: 0,
          updated_assets: 0,
          skipped_assets: 0,
          errors: [err.message || 'Synchronization request failed.'],
          duration_ms: 0,
        },
      });
    } finally {
      setSyncingId(null);
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'CONNECTED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Connected
          </span>
        );
      case 'NOT_CONFIGURED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            <HelpCircle className="w-3.5 h-3.5 text-slate-500" /> Not Configured
          </span>
        );
      case 'AUTH_FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3.5 h-3.5 text-rose-600" /> Authentication Failed
          </span>
        );
      case 'PERMISSION_DENIED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Permission Denied
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-200">
            <AlertTriangle className="w-3.5 h-3.5 text-red-600" /> {status}
          </span>
        );
    }
  };

  if (!isAdmin) {
    return (
      <div className="max-w-3xl mx-auto py-16 px-4 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 text-slate-600 flex items-center justify-center mx-auto shadow-sm">
          <Lock className="w-8 h-8 text-slate-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            Administrator Authorization Required
          </h1>
          <p className="text-sm text-gray-500 max-w-md mx-auto">
            Technical connector settings, service-principal OAuth configurations, and raw BI metadata
            synchronization are restricted to <strong>Platform Administrators</strong>.
          </p>
        </div>
        <div className="p-4 rounded-xl bg-gray-50 border border-gray-200 text-xs text-gray-600 max-w-md mx-auto text-left space-y-1.5">
          <div className="font-semibold text-gray-800">Current Role: {currentRole}</div>
          <p className="text-[11px] text-gray-500">
            Ordinary business users manage analytics through the Command Center, Asset Portfolio, Governance
            Console, and Alert Centre.
          </p>
        </div>
        <div className="pt-2">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-midnight-900 hover:bg-midnight-800 text-white text-xs font-semibold shadow-sm transition-colors"
          >
            Return to Command Center
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              Enterprise BI Platform Integrations
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 text-xs font-semibold">
              Provider-Independent
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Governed metadata connectors for Microsoft Power BI REST APIs and Tableau Server / Cloud.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadIntegrations}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Status
          </button>
          <Link
            href="/monitoring"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-intelligence text-white text-xs font-medium hover:bg-blue-700 transition-colors shadow-sm"
          >
            <Activity className="w-3.5 h-3.5" />
            Monitoring Dashboard
          </Link>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600" />
            <span>{error}</span>
          </div>
          <button onClick={loadIntegrations} className="font-semibold underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {/* Architecture Assurance Banner */}
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-intelligence shrink-0 mt-0.5" />
        <div className="text-xs text-slate-700 space-y-1">
          <div className="font-bold text-slate-900">Truthful Enterprise Integration & Credential Safety</div>
          <p>
            BIOS enforces strict security boundaries: credentials are never hardcoded or returned via API contracts.
            If live environment variables are omitted, connectors honestly report a <strong>NOT CONFIGURED</strong> status
            rather than fabricating mock connectivity. External metadata ingestion is completely idempotent and preserves
            existing synthetic challenge datasets.
          </p>
        </div>
      </div>

      {/* Connectors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {loading && integrations.length === 0 ? (
          <div className="col-span-2 p-12 text-center text-sm text-gray-400 bg-white rounded-xl border border-gray-200">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-intelligence mb-2" />
            Loading connector status...
          </div>
        ) : (
          integrations.map((conn) => {
            const isPbi = conn.connector_id === 'powerbi';
            const isTesting = testingId === conn.connector_id;
            const isSyncing = syncingId === conn.connector_id;
            const activeTestRes = testResult?.id === conn.connector_id ? testResult.result : null;
            const activeSyncRes = syncResult?.id === conn.connector_id ? syncResult.result : null;

            return (
              <div
                key={conn.connector_id}
                className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col justify-between"
              >
                <div className="p-6 space-y-5">
                  {/* Card Header */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center font-bold text-white shadow-sm ${
                        isPbi ? 'bg-amber-600' : 'bg-blue-600'
                      }`}>
                        {isPbi ? <Layers className="w-6 h-6" /> : <Server className="w-6 h-6" />}
                      </div>
                      <div>
                        <h2 className="text-base font-bold text-gray-900">{conn.connector_name}</h2>
                        <span className="text-xs text-gray-500 font-mono">Platform: {conn.platform}</span>
                      </div>
                    </div>
                    {getStatusBadge(conn.status)}
                  </div>

                  {/* Telemetry Stats */}
                  <div className="grid grid-cols-3 gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100 text-center">
                    <div>
                      <div className="text-lg font-bold text-gray-900 font-mono">{conn.discovered_workspaces}</div>
                      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
                        {isPbi ? 'Workspaces' : 'Projects'}
                      </div>
                    </div>
                    <div>
                      <div className="text-lg font-bold text-gray-900 font-mono">{conn.discovered_reports}</div>
                      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
                        {isPbi ? 'Reports' : 'Workbooks'}
                      </div>
                    </div>
                    <div>
                      <div className="text-lg font-bold text-gray-900 font-mono">{conn.discovered_models}</div>
                      <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
                        {isPbi ? 'Datasets' : 'Datasources'}
                      </div>
                    </div>
                  </div>

                  {/* Auth & Environment Disclosure */}
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-500">Authentication Method:</span>
                      <span className="font-semibold text-gray-900 font-mono uppercase">{conn.auth_type.replace('_', ' ')}</span>
                    </div>
                    <div className="flex items-center justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-500">Last Probe:</span>
                      <span className="font-mono text-gray-700">
                        {conn.last_tested_at ? new Date(conn.last_tested_at).toLocaleString() : 'Never'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-500">Last Synchronization:</span>
                      <span className="font-mono text-gray-700">
                        {conn.last_synced_at ? new Date(conn.last_synced_at).toLocaleString() : 'Never'}
                      </span>
                    </div>
                  </div>

                  {/* Unconfigured Alert / Missing Env Vars */}
                  {conn.status === 'NOT_CONFIGURED' && (
                    <div className="p-3.5 rounded-lg bg-amber-50/70 border border-amber-200 text-xs space-y-2">
                      <div className="flex items-center gap-1.5 font-bold text-amber-900">
                        <KeyRound className="w-3.5 h-3.5 text-amber-700" />
                        Required Host Environment Configuration
                      </div>
                      <p className="text-amber-800 text-[11px] leading-relaxed">
                        To enable live metadata synchronization with {conn.connector_name}, define the following environment variables in your secure key vault or <code>.env</code> file:
                      </p>
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {conn.required_env_vars.map((v) => (
                          <span
                            key={v}
                            className="px-2 py-0.5 rounded bg-white border border-amber-300 font-mono text-[10px] text-amber-900 font-semibold"
                          >
                            {v}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Connection Test Feedback */}
                  {activeTestRes && (
                    <div className={`p-3 rounded-lg text-xs space-y-1 border ${
                      activeTestRes.status === 'CONNECTED'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : 'bg-rose-50 border-rose-200 text-rose-800'
                    }`}>
                      <div className="font-bold flex items-center justify-between">
                        <span>Connection Result: {activeTestRes.status}</span>
                        {activeTestRes.latency_ms && <span className="font-mono text-[10px]">{activeTestRes.latency_ms}ms</span>}
                      </div>
                      <div>{activeTestRes.message}</div>
                    </div>
                  )}

                  {/* Sync Feedback */}
                  {activeSyncRes && (
                    <div className={`p-3 rounded-lg text-xs space-y-1 border ${
                      activeSyncRes.status === 'SUCCESS'
                        ? 'bg-blue-50 border-blue-200 text-blue-800'
                        : 'bg-rose-50 border-rose-200 text-rose-800'
                    }`}>
                      <div className="font-bold">Synchronization Status: {activeSyncRes.status}</div>
                      <div>
                        Imported: {activeSyncRes.imported_reports} reports, {activeSyncRes.imported_models} models. Updated: {activeSyncRes.updated_assets}.
                      </div>
                      {activeSyncRes.errors.length > 0 && (
                        <div className="text-rose-700 font-mono text-[11px]">
                          Errors: {activeSyncRes.errors.join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Card Actions Footer */}
                <div className="p-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between gap-3">
                  <button
                    onClick={() => handleTestConnection(conn.connector_id)}
                    disabled={isTesting || isSyncing}
                    className="flex-1 py-2 px-3 rounded-lg border border-gray-300 bg-white hover:bg-gray-100 text-xs font-semibold text-gray-700 transition-colors shadow-sm disabled:opacity-50"
                  >
                    {isTesting ? 'Testing...' : 'Test Connection'}
                  </button>
                  <button
                    onClick={() => handleSync(conn.connector_id)}
                    disabled={isTesting || isSyncing}
                    className="flex-1 py-2 px-3 rounded-lg bg-midnight-900 hover:bg-midnight-800 text-white text-xs font-semibold transition-colors shadow-sm disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
                    {isSyncing ? 'Syncing...' : 'Sync Catalogue'}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

