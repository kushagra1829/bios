'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/layout/Shell';
import { api } from '@/lib/api';
import {
  ApprovalRequest,
  ApprovalQueueSummary,
  ApprovalTransition,
  AnalyticsAsset,
  CanonicalKpi,
} from '@/lib/types';
import { ROLE_DEFINITIONS, RoleType } from '@/lib/permissions';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  FileText,
  UserCheck,
  RefreshCw,
  Search,
  ChevronRight,
  Filter,
  ExternalLink,
  ShieldCheck,
  UserX,
  History,
  Check,
  AlertTriangle,
  Layers,
  Inbox,
  ArrowRight,
  Sparkles,
  Plus,
  X,
  Building2,
  Target,
  FileCheck,
} from 'lucide-react';

const PRODUCTS = ['Nubeqa', 'Kerendia', 'Beyonttra', 'Eylea', 'Xarelto', 'Hyrnuo', 'Lynkuet', 'Aliqopa'];
const MARKETS = ['Global', 'Europe', 'US', 'DE (Germany)', 'FR (France)', 'FI (Finland)', 'JP (Japan)', 'CN (China)', 'EMEA'];
const ACTIONS = [
  { value: 'REUSE', label: 'REUSE — Existing governed asset for new need', badge: 'bg-sky-50 text-sky-700 border-sky-200' },
  { value: 'MODIFY', label: 'MODIFY — Extend existing asset metrics/filters', badge: 'bg-blue-50 text-blue-700 border-blue-200' },
  { value: 'CONSOLIDATE', label: 'CONSOLIDATE — Rationalize overlapping reports', badge: 'bg-purple-50 text-purple-700 border-purple-200' },
  { value: 'RETIRE', label: 'RETIRE — Decommission unused/legacy report', badge: 'bg-rose-50 text-rose-700 border-rose-200' },
  { value: 'BUILD_NEW', label: 'BUILD_NEW — Provision new asset for unmet need', badge: 'bg-amber-50 text-amber-700 border-amber-200' },
];

const FALLBACK_CATALOG_ASSETS: AnalyticsAsset[] = [
  {
    asset_id: 'AST-0240',
    asset_name: 'Nubeqa Commercial Performance Dashboard',
    asset_type: 'Report',
    platform: 'Power BI',
    lifecycle_status: 'active',
    endorsement: 'certified',
    owner_id: 'OWN-001',
    owner_name: 'Nina Garcia',
    product_scope: 'Nubeqa',
    market_scope: 'France',
  },
  {
    asset_id: 'AST-0014',
    asset_name: 'Kerendia Global Market Access Monitor',
    asset_type: 'Report',
    platform: 'Power BI',
    lifecycle_status: 'active',
    endorsement: 'certified',
    owner_id: 'OWN-001',
    owner_name: 'Nina Garcia',
    product_scope: 'Kerendia',
    market_scope: 'Global',
  },
  {
    asset_id: 'AST-0247',
    asset_name: 'Nubeqa Global Launch & Uptake Tracker',
    asset_type: 'Report',
    platform: 'Power BI',
    lifecycle_status: 'active',
    endorsement: 'certified',
    owner_id: 'OWN-001',
    owner_name: 'Nina Garcia',
    product_scope: 'Nubeqa',
    market_scope: 'Global',
  },
  {
    asset_id: 'AST-0001',
    asset_name: 'Executive Commercial Summary',
    asset_type: 'Report',
    platform: 'Power BI',
    lifecycle_status: 'active',
    endorsement: 'certified',
    owner_id: 'OWN-002',
    owner_name: 'Marcus Vance',
    product_scope: 'General',
    market_scope: 'Global',
  },
];

export default function ApprovalsPage() {
  const { currentActor, currentRole } = useAuth();
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [summary, setSummary] = useState<ApprovalQueueSummary | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('PENDING');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Inspector & Adjudication Workspace
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [transitions, setTransitions] = useState<ApprovalTransition[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Adjudication Modal State
  const [modalAction, setModalAction] = useState<'APPROVE' | 'REJECT' | 'REQUEST_CHANGES' | null>(null);
  const [decisionNotes, setDecisionNotes] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);

  // New Request Drawer State (Requester)
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [catalogAssets, setCatalogAssets] = useState<AnalyticsAsset[]>(FALLBACK_CATALOG_ASSETS);
  const [catalogKpis, setCatalogKpis] = useState<CanonicalKpi[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState<boolean>(false);
  const [assetSearch, setAssetSearch] = useState<string>('');

  // New Request Form State
  const [formTitle, setFormTitle] = useState<string>('');
  const [formAction, setFormAction] = useState<string>('REUSE');
  const [formPurpose, setFormPurpose] = useState<string>('');
  const [formTargetAsset, setFormTargetAsset] = useState<string>('');
  const [formProduct, setFormProduct] = useState<string>('');
  const [formMarket, setFormMarket] = useState<string>('');
  const [formKpis, setFormKpis] = useState<string[]>([]);
  const [formJustification, setFormJustification] = useState<string>('');
  const [formExpectedOutcome, setFormExpectedOutcome] = useState<string>('');
  const [formEvidenceRef, setFormEvidenceRef] = useState<string>('');
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [submittingRequest, setSubmittingRequest] = useState<boolean>(false);

  const isRequester = currentRole === 'REQUESTER';

  const fetchApprovals = async () => {
    setLoading(true);
    setError(null);
    try {
      const statusParam = filterStatus === 'ALL' ? undefined : filterStatus;
      const [data, summaryData] = await Promise.all([
        api.getApprovals(statusParam),
        api.getApprovalSummary().catch(() => null),
      ]);
      setRequests(data);
      if (summaryData) setSummary(summaryData);
      if (data.length > 0 && (!selectedRequestId || !data.some((r) => r.approval_id === selectedRequestId))) {
        setSelectedRequestId(data[0].approval_id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load approvals queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
  }, [filterStatus, currentRole, currentActor]);

  // Load catalog data for the drawer
  useEffect(() => {
    if (isDrawerOpen) {
      setLoadingCatalog(true);
      Promise.all([
        api.getAssets(400).catch(() => []),
        api.getKpis(100).catch(() => []),
      ])
        .then(([assets, kpis]) => {
          if (Array.isArray(assets) && assets.length > 0) {
            const map = new Map<string, AnalyticsAsset>();
            FALLBACK_CATALOG_ASSETS.forEach((a) => map.set(a.asset_id, a));
            assets.forEach((a) => map.set(a.asset_id, a));
            setCatalogAssets(Array.from(map.values()));
          }
          if (Array.isArray(kpis) && kpis.length > 0) {
            setCatalogKpis(kpis);
          }
        })
        .finally(() => setLoadingCatalog(false));
    }
  }, [isDrawerOpen]);

  // Fetch transition history when selected request changes
  useEffect(() => {
    if (!selectedRequestId) {
      setTransitions([]);
      return;
    }
    let isCancelled = false;
    setLoadingHistory(true);
    api
      .getApprovalHistory(selectedRequestId)
      .then((history) => {
        if (!isCancelled) setTransitions(history);
      })
      .catch(() => {
        if (!isCancelled) setTransitions([]);
      })
      .finally(() => {
        if (!isCancelled) setLoadingHistory(false);
      });
    return () => {
      isCancelled = true;
    };
  }, [selectedRequestId]);

  const filteredRequests = useMemo(() => {
    if (!searchQuery.trim()) return requests;
    const q = searchQuery.toLowerCase().trim();
    return requests.filter(
      (r) =>
        r.approval_id.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q) ||
        r.target_entity_id.toLowerCase().includes(q) ||
        r.requester_id.toLowerCase().includes(q) ||
        r.action_type.toLowerCase().includes(q)
    );
  }, [requests, searchQuery]);

  const selectedRequest = requests.find((r) => r.approval_id === selectedRequestId) || filteredRequests[0] || null;

  // Filtered and prioritized assets for dropdown
  const sortedAndFilteredCatalogAssets = useMemo(() => {
    const q = assetSearch.toLowerCase().trim();
    const filtered = catalogAssets.filter((a) => {
      if (!q) return true;
      return (
        a.asset_id.toLowerCase().includes(q) ||
        a.asset_name.toLowerCase().includes(q) ||
        (a.product_scope && a.product_scope.toLowerCase().includes(q)) ||
        (a.market_scope && a.market_scope.toLowerCase().includes(q)) ||
        (a.owner_id && a.owner_id.toLowerCase().includes(q)) ||
        (a.owner_name && a.owner_name.toLowerCase().includes(q))
      );
    });

    // Sort: assets owned by OWN-001 (Nina Garcia, the active Asset Owner) first, then alphabetical by asset_id
    return filtered.sort((a, b) => {
      const aIsOwn = a.owner_id === 'OWN-001';
      const bIsOwn = b.owner_id === 'OWN-001';
      if (aIsOwn && !bIsOwn) return -1;
      if (!aIsOwn && bIsOwn) return 1;
      return a.asset_id.localeCompare(b.asset_id);
    });
  }, [catalogAssets, assetSearch]);

  const selectedAssetDetails = useMemo(() => {
    if (!formTargetAsset.trim()) return null;
    return (
      catalogAssets.find(
        (a) => a.asset_id.toUpperCase() === formTargetAsset.trim().toUpperCase()
      ) || null
    );
  }, [catalogAssets, formTargetAsset]);

  const handleSelectAsset = (assetId: string) => {
    const cleanId = assetId.trim().toUpperCase();
    if (!cleanId) {
      setFormTargetAsset('');
      return;
    }
    setFormTargetAsset(cleanId);
    setAssetSearch('');
    if (formErrors.targetAsset) {
      setFormErrors((prev) => ({ ...prev, targetAsset: '' }));
    }
    const matched = catalogAssets.find((a) => a.asset_id.toUpperCase() === cleanId);
    if (matched) {
      if (!formProduct && matched.product_scope) {
        setFormProduct(matched.product_scope);
      }
      if (!formMarket && matched.market_scope) {
        setFormMarket(matched.market_scope);
      }
      if (formKpis.length === 0) {
        setFormKpis(['Net Sales', 'Net Sales Growth']);
      }
    }
  };

  const handleAssetSearchChange = (val: string) => {
    setAssetSearch(val);
    const clean = val.trim().toUpperCase();
    if (clean) {
      setFormTargetAsset(clean);
      if (formErrors.targetAsset) {
        setFormErrors((prev) => ({ ...prev, targetAsset: '' }));
      }
      const matched = catalogAssets.find((a) => a.asset_id.toUpperCase() === clean);
      if (matched) {
        if (!formProduct && matched.product_scope) {
          setFormProduct(matched.product_scope);
        }
        if (!formMarket && matched.market_scope) {
          setFormMarket(matched.market_scope);
        }
        if (formKpis.length === 0) {
          setFormKpis(['Net Sales', 'Net Sales Growth']);
        }
      }
    }
  };

  // Parse evidence, blockers, and warnings safely
  const parsedBlockers: string[] = useMemo(() => {
    if (!selectedRequest?.blockers_json) return [];
    try {
      const parsed = JSON.parse(selectedRequest.blockers_json);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [selectedRequest]);

  const parsedWarnings: string[] = useMemo(() => {
    if (!selectedRequest?.warnings_json) return [];
    try {
      const parsed = JSON.parse(selectedRequest.warnings_json);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [selectedRequest]);

  const parsedEvidence: any[] = useMemo(() => {
    if (!selectedRequest?.evidence_snapshot_json) return [];
    try {
      const parsed = JSON.parse(selectedRequest.evidence_snapshot_json);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [selectedRequest]);

  const handleOpenModal = (action: 'APPROVE' | 'REJECT' | 'REQUEST_CHANGES') => {
    setModalAction(action);
    setDecisionNotes('');
    setError(null);
    setActionSuccess(null);
  };

  const handleCloseModal = () => {
    setModalAction(null);
    setDecisionNotes('');
  };

  const executeAction = async () => {
    if (!selectedRequest || !modalAction) return;

    if (!decisionNotes.trim() || decisionNotes.trim().length < 5) {
      setError('A substantive decision rationale (minimum 5 characters) is required by governance policy (RULE-008).');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      if (modalAction === 'APPROVE') {
        await api.approveRequest(
          selectedRequest.approval_id,
          currentActor,
          currentRole,
          decisionNotes.trim()
        );
        setActionSuccess(`Approval granted for ${selectedRequest.approval_id}. Action authorized under role ${currentRole}.`);
      } else if (modalAction === 'REJECT') {
        await api.rejectRequest(
          selectedRequest.approval_id,
          currentActor,
          currentRole,
          decisionNotes.trim()
        );
        setActionSuccess(`Request ${selectedRequest.approval_id} rejected.`);
      } else if (modalAction === 'REQUEST_CHANGES') {
        await api.requestChanges(
          selectedRequest.approval_id,
          currentActor,
          currentRole,
          decisionNotes.trim()
        );
        setActionSuccess(`Modification requested for ${selectedRequest.approval_id}. Returned to requester.`);
      }

      handleCloseModal();
      await fetchApprovals();
    } catch (err: any) {
      setError(`Backend Authorization Rejected: ${err.message || 'Action failed'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const validateNewRequestForm = () => {
    const errors: Record<string, string> = {};
    if (!formTitle.trim() || formTitle.trim().length < 5) {
      errors.title = 'Title must be at least 5 characters.';
    }
    if (!formAction) {
      errors.action = 'Please select a request action type.';
    }
    if (!formPurpose.trim() || formPurpose.trim().length < 10) {
      errors.purpose = 'Business purpose and description must be at least 10 characters.';
    }
    if (formAction !== 'BUILD_NEW' && !formTargetAsset.trim()) {
      errors.targetAsset = 'Target asset is required for this action type.';
    }
    if (!formJustification.trim() || formJustification.trim().length < 5) {
      errors.justification = 'Business justification must be at least 5 characters.';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreateRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateNewRequestForm()) return;

    setSubmittingRequest(true);
    setError(null);

    const fullDescription = `${formPurpose.trim()}\n\nBusiness Justification:\n${formJustification.trim()}${
      formExpectedOutcome.trim() ? `\n\nExpected Outcome:\n${formExpectedOutcome.trim()}` : ''
    }`;

    const evidenceSnapshot: Record<string, any> = {
      product: formProduct || undefined,
      market: formMarket || undefined,
      kpis: formKpis.length > 0 ? formKpis : undefined,
      justification: formJustification.trim(),
      expected_outcome: formExpectedOutcome.trim() || undefined,
      evidence_reference: formEvidenceRef.trim() || undefined,
    };

    try {
      const created = await api.submitApprovalRequest({
        title: formTitle.trim(),
        action_type: formAction,
        description: fullDescription,
        target_entity_type: 'asset',
        target_entity_id: formAction === 'BUILD_NEW' ? (formTargetAsset.trim() || undefined) : formTargetAsset.trim(),
        recommendation_ref: formEvidenceRef.trim() || undefined,
        evidence_snapshot: evidenceSnapshot,
      });

      // Reset form
      setFormTitle('');
      setFormPurpose('');
      setFormTargetAsset('');
      setFormProduct('');
      setFormMarket('');
      setFormKpis([]);
      setFormJustification('');
      setFormExpectedOutcome('');
      setFormEvidenceRef('');
      setFormErrors({});
      setIsDrawerOpen(false);

      setActionSuccess(
        `Approval request ${created.approval_id} submitted successfully! Initial status: PENDING, assigned to ${created.required_role}.`
      );

      // Refresh list and select the newly created request
      await fetchApprovals();
      setSelectedRequestId(created.approval_id);
    } catch (err: any) {
      setError(`Failed to submit request: ${err.message || 'Backend validation error'}`);
    } finally {
      setSubmittingRequest(false);
    }
  };

  const toggleKpi = (kpiName: string) => {
    setFormKpis((prev) =>
      prev.includes(kpiName) ? prev.filter((k) => k !== kpiName) : [...prev, kpiName]
    );
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PENDING':
        return 'bg-amber-50 text-amber-800 border-amber-200';
      case 'APPROVED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200';
      case 'REJECTED':
        return 'bg-rose-50 text-rose-800 border-rose-200';
      case 'CHANGES_REQUESTED':
        return 'bg-indigo-50 text-indigo-800 border-indigo-200';
      default:
        return 'bg-slate-50 text-slate-800 border-slate-200';
    }
  };

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'REUSE':
        return 'bg-sky-50 text-sky-700 border-sky-200';
      case 'MODIFY':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'CONSOLIDATE':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'RETIRE':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case 'BUILD_NEW':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getTabCount = (status: string) => {
    if (!summary) return null;
    switch (status) {
      case 'PENDING':
        return summary.total_pending;
      case 'APPROVED':
        return summary.total_approved;
      case 'REJECTED':
        return summary.total_rejected;
      case 'CHANGES_REQUESTED':
        return summary.total_changes_requested;
      case 'ALL':
        return (
          (summary.total_pending || 0) +
          (summary.total_approved || 0) +
          (summary.total_rejected || 0) +
          (summary.total_changes_requested || 0)
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-midnight-900">
              {isRequester ? 'My Submitted Approval Requests' : 'Enterprise Approvals & Human Adjudication'}
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-intelligence text-xs font-semibold">
              {isRequester ? 'Personal Request Tracking' : 'Mandatory Oversight Center'}
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {isRequester
              ? 'Submit, track, and monitor governance sign-offs for your analytics modifications and provisioning requests.'
              : 'Authoritative human-in-the-loop governance sign-off. Enforces live owner authority (N4), synchronous waiver validation (N5), and full audit logging.'}
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          {/* New Request Button: Prominently featured for Requester */}
          {isRequester && (
            <button
              onClick={() => {
                setIsDrawerOpen(true);
                setFormErrors({});
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-intelligence text-white text-xs font-semibold hover:bg-blue-700 transition-colors shadow-sm cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              New Request
            </button>
          )}

          <button
            onClick={fetchApprovals}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors shadow-2xs cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-intelligence' : 'text-gray-500'}`} />
            Refresh Queue
          </button>
        </div>
      </div>

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="font-bold text-emerald-600 hover:text-emerald-800 cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-critical-50 border border-critical-200 text-critical-700 text-xs font-medium flex items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-critical shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="font-bold text-critical hover:text-red-900 cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {/* Security Invariant Callout */}
      <div className="p-3.5 bg-slate-900 text-slate-100 rounded-xl text-xs flex items-center justify-between shadow-2xs">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>
            <strong>Deterministic Governance Boundaries:</strong> Enforcing live database owner employment verification (N4), point-of-use waiver expiry (N5), and anti-self-approval restrictions.
          </span>
        </div>
        <span className="text-[11px] text-slate-400 font-medium hidden sm:inline">
          Workspace: <strong>{ROLE_DEFINITIONS[currentRole as RoleType]?.title || currentRole}</strong> ({currentActor})
        </span>
      </div>

      {/* Filter Tabs with Live Database Counts */}
      <div className="flex items-center gap-1.5 border-b border-gray-200 overflow-x-auto pb-1">
        {['PENDING', 'ALL', 'APPROVED', 'REJECTED', 'CHANGES_REQUESTED'].map((status) => {
          const count = getTabCount(status);
          const isSelected = filterStatus === status;

          return (
            <button
              key={status}
              onClick={() => {
                setFilterStatus(status);
                setSelectedRequestId(null);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all flex items-center gap-1.5 shrink-0 cursor-pointer ${
                isSelected
                  ? 'bg-midnight-900 text-white shadow-2xs'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <span>{status.replace('_', ' ')}</span>
              {count !== null && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    isSelected ? 'bg-white/20 text-white' : 'bg-gray-200 text-gray-700'
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Main Split-Screen Adjudication Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left Column: Approval Requests Queue (2 Columns) */}
        <div className="lg:col-span-2 space-y-3">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ID, requester, asset, or title..."
              className="w-full pl-8 pr-3 py-2 text-xs border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence"
            />
          </div>

          <div className="flex items-center justify-between text-xs text-gray-500 font-medium px-0.5">
            <span>
              {isRequester ? 'My Requests' : 'Requests in Queue'} ({filteredRequests.length})
            </span>
            <span>Sorted by Submission (Newest First)</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-xs text-gray-400 bg-white rounded-xl border border-gray-200 shadow-2xs">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto text-intelligence mb-2" />
              Loading approval requests from database...
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="p-12 text-center text-xs text-gray-400 bg-white rounded-xl border border-gray-200 shadow-2xs space-y-3">
              <Inbox className="w-8 h-8 mx-auto text-gray-300" />
              <p className="font-semibold text-gray-700">
                {isRequester
                  ? 'No approval requests matching this filter.'
                  : `No approval requests matching status '${filterStatus}'.`}
              </p>
              {isRequester && (
                <button
                  onClick={() => setIsDrawerOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-intelligence text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-colors mx-auto cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Submit Your First Request
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
              {filteredRequests.map((req) => {
                const isSelected = selectedRequest?.approval_id === req.approval_id;

                return (
                  <div
                    key={req.approval_id}
                    onClick={() => setSelectedRequestId(req.approval_id)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 text-xs ${
                      isSelected
                        ? 'bg-blue-50/70 border-intelligence ring-1 ring-intelligence shadow-2xs'
                        : 'bg-white border-gray-200 hover:border-gray-300 hover:bg-gray-50/60 shadow-2xs'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-gray-800">{req.approval_id}</span>
                        <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${getActionBadge(req.action_type)}`}>
                          {req.action_type}
                        </span>
                      </div>
                      <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-full border ${getStatusBadge(req.status)}`}>
                        {req.status}
                      </span>
                    </div>

                    <div className="font-bold text-gray-900 line-clamp-1">{req.title}</div>
                    <p className="text-[11px] text-gray-500 line-clamp-2 leading-snug">{req.description}</p>

                    <div className="flex items-center justify-between text-[10px] text-gray-400 font-mono pt-1.5 border-t border-gray-100">
                      <span>Requester: {req.requester_id}</span>
                      <span>Target: {req.target_entity_id}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Detailed Adjudication Workspace (3 Columns) */}
        <div className="lg:col-span-3">
          {selectedRequest ? (
            <div className="p-6 bg-white rounded-xl border border-gray-200 shadow-sm space-y-5">
              {/* Header */}
              <div className="border-b border-gray-100 pb-4 space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-extrabold px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">
                      {selectedRequest.approval_id}
                    </span>
                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${getActionBadge(selectedRequest.action_type)}`}>
                      {selectedRequest.action_type}
                    </span>
                    <span className={`text-xs font-bold uppercase px-2.5 py-0.5 rounded-full border ${getStatusBadge(selectedRequest.status)}`}>
                      {selectedRequest.status}
                    </span>
                  </div>

                  <span className="text-xs text-gray-400 font-mono">
                    Submitted: {new Date(selectedRequest.created_at).toLocaleString()}
                  </span>
                </div>

                <h2 className="text-lg font-bold text-midnight-900">{selectedRequest.title}</h2>
                <div className="text-xs text-gray-700 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-200/80 font-sans space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">Requester Rationale & Scope:</span>
                  <p className="whitespace-pre-line">{selectedRequest.description}</p>
                </div>
              </div>

              {/* Scope & Role Requirements */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs bg-gray-50/70 p-3.5 rounded-lg border border-gray-200">
                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Target Entity</span>
                  {selectedRequest.target_entity_id.startsWith('AST-') ? (
                    <Link
                      href={`/assets/${selectedRequest.target_entity_id}`}
                      className="font-mono font-bold text-intelligence hover:underline inline-flex items-center gap-1"
                    >
                      {selectedRequest.target_entity_id} <ExternalLink className="w-3 h-3" />
                    </Link>
                  ) : (
                    <span className="font-mono font-bold text-gray-800">{selectedRequest.target_entity_id}</span>
                  )}
                </div>

                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Action Type</span>
                  <span className="font-semibold text-gray-900">{selectedRequest.action_type}</span>
                </div>

                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Required Reviewer Role</span>
                  <span className="font-mono font-semibold text-purple-700">{selectedRequest.required_role}</span>
                </div>

                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Requester ID</span>
                  <span className="font-mono text-gray-700">{selectedRequest.requester_id}</span>
                </div>

                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Recommendation Ref</span>
                  <span className="font-mono text-gray-700">{selectedRequest.recommendation_ref || 'N/A'}</span>
                </div>

                <div>
                  <span className="text-gray-400 block mb-0.5 text-[11px]">Authority Barrier</span>
                  <span className="text-gray-700 font-medium">Asset Owner Custody Enforced</span>
                </div>
              </div>

              {/* Dedicated Governance Evidence & Blockers Section */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gray-800 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-intelligence" />
                    Governance Evidence & Safeguard Findings
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {parsedBlockers.length} Blocker(s), {parsedWarnings.length} Review Item(s)
                  </span>
                </div>

                {parsedBlockers.length === 0 && parsedWarnings.length === 0 && parsedEvidence.length === 0 ? (
                  <div className="p-3 bg-emerald-50/60 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>No active governance blockers or risk warnings. Baseline validation passed.</span>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {/* Blockers */}
                    {parsedBlockers.map((blocker, idx) => (
                      <div key={`blk-${idx}`} className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-start gap-2">
                        <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-bold uppercase tracking-wider text-[10px] bg-rose-200/80 text-rose-900 px-1.5 py-0.2 rounded mr-1.5">
                            BLOCKER
                          </span>
                          <span>{blocker}</span>
                        </div>
                      </div>
                    ))}

                    {/* Warnings & Evidence Items */}
                    {parsedWarnings.map((warning, idx) => (
                      <div key={`wrn-${idx}`} className="p-3 bg-amber-50/70 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-bold uppercase tracking-wider text-[10px] bg-amber-200/80 text-amber-900 px-1.5 py-0.2 rounded mr-1.5">
                            REQUIRES REVIEW
                          </span>
                          <span>{warning}</span>
                        </div>
                      </div>
                    ))}

                    {/* Snapshot Structured Evidence (if not listed above) */}
                    {parsedEvidence.length > 0 && parsedBlockers.length === 0 && parsedWarnings.length === 0 && (
                      <div className="space-y-1.5">
                        {parsedEvidence.map((ev, idx) => (
                          <div key={`ev-${idx}`} className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 flex items-center justify-between">
                            <span className="font-semibold">{ev.evidence_type || 'Evidence'}: {ev.evidence_item || ev.evidence_summary}</span>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 text-slate-800">
                              {ev.evidence_status || 'VERIFIED'}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Decision History & Transition Audit Trail */}
              <div className="space-y-2.5 pt-2 border-t border-gray-100">
                <span className="text-xs font-bold text-gray-800 uppercase tracking-wider flex items-center gap-1.5">
                  <History className="w-3.5 h-3.5 text-intelligence" />
                  Decision History & Transition Audit Trail
                </span>

                {loadingHistory ? (
                  <div className="p-4 text-center text-xs text-gray-400">Loading audit history...</div>
                ) : transitions.length === 0 ? (
                  <div className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-500">
                    No transition history recorded for this request.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {transitions.map((trn) => (
                      <div
                        key={trn.transition_id}
                        className="p-3 rounded-lg bg-slate-50/80 border border-slate-200 text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between text-[11px]">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-900">{trn.actor_id}</span>
                            <span className="text-slate-400">({trn.actor_role})</span>
                            <span className="font-mono text-slate-400">→</span>
                            <span className={`px-1.5 py-0.2 rounded font-bold text-[9px] uppercase border ${getStatusBadge(trn.to_state)}`}>
                              {trn.to_state}
                            </span>
                          </div>
                          <span className="text-slate-400 font-mono text-[10px]">
                            {new Date(trn.transitioned_at).toLocaleString()}
                          </span>
                        </div>
                        {trn.comment && (
                          <p className="text-slate-700 italic pl-2 border-l-2 border-slate-300">
                            "{trn.comment}"
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Decided Outcome Details (If Already Adjudicated) */}
              {selectedRequest.status !== 'PENDING' && (
                <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1.5">
                  <div className="font-bold text-slate-900 flex items-center gap-1.5">
                    <UserCheck className="w-4 h-4 text-intelligence" />
                    Final Adjudication Record:
                  </div>
                  <div>
                    Decided by: <strong>{selectedRequest.decided_by_id}</strong> ({selectedRequest.decided_by_role || 'REVIEWER'})
                  </div>
                  <div>
                    Decision Rationale: <em>"{selectedRequest.decision_reason || 'No recorded note'}"</em>
                  </div>
                  {selectedRequest.decided_at && (
                    <div className="text-[11px] text-gray-400">
                      Timestamp: {new Date(selectedRequest.decided_at).toLocaleString()}
                    </div>
                  )}
                </div>
              )}

              {/* Action Controls */}
              {selectedRequest.status === 'PENDING' ? (
                isRequester ? (
                  <div className="p-3.5 bg-blue-50/80 border border-blue-200 rounded-lg text-xs text-blue-900 flex items-center gap-2">
                    <Clock className="w-4 h-4 text-blue-600 shrink-0" />
                    <span>
                      This request is currently <strong>Pending Review</strong> by an authorized{' '}
                      <strong>{selectedRequest.required_role}</strong>. You will be notified once a decision is recorded.
                    </span>
                  </div>
                ) : (
                  <div className="space-y-3 pt-3 border-t border-gray-100">
                    <span className="text-xs font-bold text-gray-700 uppercase tracking-wider block">
                      Adjudication Decisions (Requires Substantive Rationale):
                    </span>

                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => handleOpenModal('APPROVE')}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        Authorize & Approve
                      </button>

                      <button
                        onClick={() => handleOpenModal('REJECT')}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
                      >
                        <XCircle className="w-4 h-4" />
                        Reject Request
                      </button>

                      <button
                        onClick={() => handleOpenModal('REQUEST_CHANGES')}
                        className="px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
                      >
                        <AlertCircle className="w-4 h-4" />
                        Request Changes
                      </button>
                    </div>
                  </div>
                )
              ) : (
                <div className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-500 italic">
                  This request has been finalized ({selectedRequest.status}). Consequential actions are immutable in accordance with audit trail compliance.
                </div>
              )}
            </div>
          ) : (
            <div className="p-12 text-center text-xs text-gray-400 bg-white rounded-xl border border-gray-200 shadow-2xs">
              Select an approval request on the left to inspect evidence and execute governance decisions.
            </div>
          )}
        </div>
      </div>

      {/* Confirmation & Rationale Modal (Adjudication) */}
      {modalAction && selectedRequest && (
        <div className="fixed inset-0 bg-midnight-950/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-gray-200 shadow-xl max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-base font-bold text-midnight-900 flex items-center gap-2">
                {modalAction === 'APPROVE' && <CheckCircle2 className="w-5 h-5 text-emerald-600" />}
                {modalAction === 'REJECT' && <XCircle className="w-5 h-5 text-rose-600" />}
                {modalAction === 'REQUEST_CHANGES' && <AlertCircle className="w-5 h-5 text-amber-600" />}
                Confirm Adjudication: {modalAction.replace('_', ' ')}
              </h3>
              <button onClick={handleCloseModal} className="text-gray-400 hover:text-gray-600 font-bold cursor-pointer">
                ✕
              </button>
            </div>

            <p className="text-xs text-gray-600 leading-relaxed">
              You are executing a consequential lifecycle governance action for request{' '}
              <strong className="font-mono text-gray-900">{selectedRequest.approval_id}</strong> on target entity{' '}
              <strong className="font-mono text-gray-900">{selectedRequest.target_entity_id}</strong>.
            </p>

            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-gray-700">
                Governance Decision Reason / Rationale (Mandatory, minimum 5 characters):
              </label>
              <textarea
                rows={3}
                value={decisionNotes}
                onChange={(e) => setDecisionNotes(e.target.value)}
                placeholder="State the governance justification, policy reference, or rationale for this approval decision..."
                className="w-full p-2.5 border border-gray-300 rounded-lg text-xs text-midnight-900 focus:outline-none focus:ring-2 focus:ring-intelligence"
                required
              />
            </div>

            <div className="p-2.5 rounded bg-slate-50 border border-slate-200 text-[11px] text-slate-700">
              Adjudicating Authority: <strong>{ROLE_DEFINITIONS[currentRole as RoleType]?.title || currentRole}</strong> ({currentActor})
            </div>

            <div className="flex items-center justify-end gap-3 pt-2 border-t">
              <button
                type="button"
                onClick={handleCloseModal}
                disabled={submitting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={executeAction}
                disabled={submitting || decisionNotes.trim().length < 5}
                className={`px-4 py-2 text-white rounded-lg text-xs font-bold shadow-sm transition-colors cursor-pointer ${
                  modalAction === 'APPROVE'
                    ? 'bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50'
                    : modalAction === 'REJECT'
                    ? 'bg-red-600 hover:bg-red-700 disabled:opacity-50'
                    : 'bg-slate-700 hover:bg-slate-800 disabled:opacity-50'
                }`}
              >
                {submitting ? 'Submitting...' : `Confirm ${modalAction.replace('_', ' ')}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Slide-over Right Drawer: New Approval Request (Requester) */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            onClick={() => !submittingRequest && setIsDrawerOpen(false)}
            className="fixed inset-0 bg-midnight-950/50 backdrop-blur-xs transition-opacity"
          />

          {/* Drawer Panel */}
          <div className="relative z-10 w-full max-w-xl bg-white shadow-2xl border-l border-gray-200 flex flex-col h-full animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-5 border-b border-gray-200 bg-slate-50/70 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-blue-100 text-intelligence">
                    <FileCheck className="w-4 h-4" />
                  </span>
                  <h2 className="text-base font-bold text-midnight-900">New Approval Request</h2>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Submit a governed request for asset reuse, modification, retirement, consolidation, or provisioning.
                </p>
              </div>

              <button
                onClick={() => setIsDrawerOpen(false)}
                disabled={submittingRequest}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Form Body */}
            <form id="new-request-form" onSubmit={handleCreateRequest} className="flex-1 overflow-y-auto p-6 space-y-4 text-xs">
              {/* 1. Request Title */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>Request Title <span className="text-rose-500">*</span></span>
                  <span className="text-[10px] text-gray-400 font-normal">Min 5 chars</span>
                </label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder="e.g. Reuse certified Nubeqa commercial report for France"
                  className={`w-full p-2.5 border rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 ${
                    formErrors.title ? 'border-rose-400 focus:ring-rose-500' : 'border-gray-300 focus:ring-intelligence'
                  }`}
                />
                {formErrors.title && <p className="text-[11px] text-rose-600 font-medium">{formErrors.title}</p>}
              </div>

              {/* 2. Action Type */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>Request Action Type <span className="text-rose-500">*</span></span>
                  <span className="text-[10px] text-gray-400 font-normal">Authoritative Review Routing</span>
                </label>
                <select
                  value={formAction}
                  onChange={(e) => setFormAction(e.target.value)}
                  className="w-full p-2.5 border border-gray-300 rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-intelligence font-medium"
                >
                  {ACTIONS.map((act) => (
                    <option key={act.value} value={act.value}>
                      {act.label}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-gray-400">
                  {formAction === 'BUILD_NEW'
                    ? 'Routes to Domain Steward for canonical semantic model and KPI evaluation.'
                    : formAction === 'RETIRE'
                    ? 'Routes to BI Governance Reviewer / Asset Owner for downstream dependency review.'
                    : 'Routes to the Asset Owner for verification against governance baseline.'}
                </p>
              </div>

              {/* 3. Business Purpose & Description */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>Business Purpose and Description <span className="text-rose-500">*</span></span>
                  <span className="text-[10px] text-gray-400 font-normal">Min 10 chars</span>
                </label>
                <textarea
                  rows={3}
                  value={formPurpose}
                  onChange={(e) => setFormPurpose(e.target.value)}
                  placeholder="Describe what business capability, reporting view, or data need is addressed by this request..."
                  className={`w-full p-2.5 border rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 ${
                    formErrors.purpose ? 'border-rose-400 focus:ring-rose-500' : 'border-gray-300 focus:ring-intelligence'
                  }`}
                />
                {formErrors.purpose && <p className="text-[11px] text-rose-600 font-medium">{formErrors.purpose}</p>}
              </div>

              {/* 4. Target Asset (Searchable Catalog) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="font-semibold text-gray-900 flex items-center gap-1">
                    <span>Target Asset</span>
                    {formAction !== 'BUILD_NEW' && <span className="text-rose-500">*</span>}
                  </label>
                  <span className="text-[10px] text-gray-400 font-normal">
                    {formAction === 'BUILD_NEW' ? 'Optional for BUILD_NEW' : 'Required (Search or Select from Catalog)'}
                  </span>
                </div>

                {formAction === 'BUILD_NEW' ? (
                  <input
                    type="text"
                    value={formTargetAsset}
                    onChange={(e) => setFormTargetAsset(e.target.value)}
                    placeholder="Auto-generated provisioning ID (leave blank or specify proposed name)"
                    className="w-full p-2.5 border border-gray-300 rounded-lg text-xs bg-gray-50 text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence font-mono"
                  />
                ) : (
                  <div className="space-y-2">
                    {/* If an asset is chosen, show a prominent confirmed asset card with a Change button */}
                    {formTargetAsset ? (
                      <div className="p-3 bg-slate-50 border border-slate-300 rounded-lg text-xs space-y-1.5 animate-in fade-in duration-150">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold text-midnight-950 bg-white px-2 py-0.5 rounded border border-slate-200">
                              {formTargetAsset}
                            </span>
                            <span className="font-semibold text-slate-800">
                              {selectedAssetDetails?.asset_name || 'Target Asset Selected'}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setFormTargetAsset('');
                              setAssetSearch('');
                            }}
                            className="text-[11px] text-blue-600 hover:text-blue-800 hover:underline font-medium cursor-pointer"
                          >
                            Change Asset
                          </button>
                        </div>
                        {selectedAssetDetails && (
                          <div className="text-[11px] text-slate-600 flex flex-wrap items-center gap-3 pt-1 border-t border-slate-200/60">
                            <span><strong>Assigned Owner:</strong> {selectedAssetDetails.owner_name || selectedAssetDetails.owner_id}</span>
                            <span><strong>Product:</strong> {selectedAssetDetails.product_scope || 'General'}</span>
                            <span><strong>Market:</strong> {selectedAssetDetails.market_scope || 'Global'}</span>
                            <span><strong>Platform:</strong> {selectedAssetDetails.platform}</span>
                          </div>
                        )}
                        <p className="text-[10px] text-slate-500 italic pt-0.5">
                          ✓ Authoritative review routes to {selectedAssetDetails?.owner_name || selectedAssetDetails?.owner_id || 'Asset Owner'} ({selectedAssetDetails?.owner_id === 'OWN-001' ? 'Current Asset Owner Workspace' : selectedAssetDetails?.owner_id}).
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {/* Primary Catalog Dropdown Selector */}
                        <select
                          value={formTargetAsset}
                          onChange={(e) => handleSelectAsset(e.target.value)}
                          className={`w-full p-2.5 border rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 font-mono cursor-pointer ${
                            formErrors.targetAsset ? 'border-rose-400 focus:ring-rose-500' : 'border-gray-300 focus:ring-intelligence'
                          }`}
                        >
                          <option value="">-- Select Target Asset from Catalog ({catalogAssets.length} available) --</option>
                          <optgroup label="Assigned to Nina Garcia (OWN-001) — Priority Review Routing">
                            {catalogAssets
                              .filter((a) => a.owner_id === 'OWN-001')
                              .map((a) => (
                                <option key={a.asset_id} value={a.asset_id}>
                                  ★ {a.asset_id} — {a.asset_name} ({a.product_scope || 'General'}, {a.market_scope || 'Global'})
                                </option>
                              ))}
                          </optgroup>
                          <optgroup label="Other Governed Portfolio Assets">
                            {catalogAssets
                              .filter((a) => a.owner_id !== 'OWN-001')
                              .map((a) => (
                                <option key={a.asset_id} value={a.asset_id}>
                                  {a.asset_id} — {a.asset_name} ({a.product_scope || 'General'}, Owner: {a.owner_name || a.owner_id || 'Unassigned'})
                                </option>
                              ))}
                          </optgroup>
                        </select>

                        {/* Direct Asset ID / Quick Search Input */}
                        <div className="flex items-center gap-2">
                          <div className="relative flex-1">
                            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                            <input
                              type="text"
                              value={assetSearch}
                              onChange={(e) => handleAssetSearchChange(e.target.value)}
                              placeholder="Or type Asset ID directly (e.g. AST-0240, AST-0014)..."
                              className="w-full pl-9 pr-3 py-1.5 text-xs border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence"
                            />
                          </div>
                          {assetSearch.trim() && (
                            <button
                              type="button"
                              onClick={() => handleSelectAsset(assetSearch.trim().toUpperCase())}
                              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-lg text-xs font-semibold text-slate-800 transition-colors cursor-pointer"
                            >
                              Select
                            </button>
                          )}
                        </div>

                        {formErrors.targetAsset && (
                          <p className="text-[11px] text-rose-600 font-medium">{formErrors.targetAsset}</p>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 5 & 6. Product & Market Scope (Grid) */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-semibold text-gray-900">Product Scope</label>
                  <select
                    value={formProduct}
                    onChange={(e) => setFormProduct(e.target.value)}
                    className="w-full p-2 border border-gray-300 rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
                  >
                    <option value="">-- All Products / Portfolio --</option>
                    {PRODUCTS.map((prod) => (
                      <option key={prod} value={prod}>
                        {prod}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-gray-900">Market / Geography</label>
                  <select
                    value={formMarket}
                    onChange={(e) => setFormMarket(e.target.value)}
                    className="w-full p-2 border border-gray-300 rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-intelligence"
                  >
                    <option value="">-- Global / Cross-Market --</option>
                    {MARKETS.map((mkt) => (
                      <option key={mkt} value={mkt.split(' ')[0]}>
                        {mkt}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 7. Required Canonical KPIs */}
              <div className="space-y-1.5">
                <label className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>Required Canonical KPI(s)</span>
                  <span className="text-[10px] text-gray-400 font-normal">Select applicable metrics</span>
                </label>
                <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto p-2 bg-slate-50 border border-slate-200 rounded-lg">
                  {catalogKpis.slice(0, 15).map((kpi) => {
                    const isSelected = formKpis.includes(kpi.kpi_name);
                    return (
                      <button
                        type="button"
                        key={kpi.kpi_id}
                        onClick={() => toggleKpi(kpi.kpi_name)}
                        className={`px-2 py-1 rounded text-[11px] font-medium border transition-colors cursor-pointer ${
                          isSelected
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-100'
                        }`}
                      >
                        {kpi.kpi_name}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 8. Business Justification */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>Business Justification <span className="text-rose-500">*</span></span>
                  <span className="text-[10px] text-gray-400 font-normal">Min 5 chars</span>
                </label>
                <textarea
                  rows={2}
                  value={formJustification}
                  onChange={(e) => setFormJustification(e.target.value)}
                  placeholder="Explain why this request is needed, business benefits, and impact on decision making..."
                  className={`w-full p-2.5 border rounded-lg text-xs bg-white text-gray-900 focus:outline-none focus:ring-1 ${
                    formErrors.justification ? 'border-rose-400 focus:ring-rose-500' : 'border-gray-300 focus:ring-intelligence'
                  }`}
                />
                {formErrors.justification && (
                  <p className="text-[11px] text-rose-600 font-medium">{formErrors.justification}</p>
                )}
              </div>

              {/* 9. Expected Outcome */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900">Expected Business Outcome (Optional)</label>
                <input
                  type="text"
                  value={formExpectedOutcome}
                  onChange={(e) => setFormExpectedOutcome(e.target.value)}
                  placeholder="e.g. Reduce report duplication and unify European commercial tracking"
                  className="w-full p-2.5 border border-gray-300 rounded-lg text-xs bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence"
                />
              </div>

              {/* 10. Supporting Reference */}
              <div className="space-y-1">
                <label className="font-semibold text-gray-900">Supporting Reference / Recommendation ID (Optional)</label>
                <input
                  type="text"
                  value={formEvidenceRef}
                  onChange={(e) => setFormEvidenceRef(e.target.value)}
                  placeholder="e.g. REC-20261108-01, REQ-DEMO-101, or ticket reference"
                  className="w-full p-2.5 border border-gray-300 rounded-lg text-xs bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-intelligence font-mono"
                />
              </div>

              {/* Security Banner inside drawer */}
              <div className="p-3 bg-slate-100 rounded-lg border border-slate-200 text-[11px] text-slate-700 space-y-1">
                <div className="flex items-center gap-1.5 font-bold text-slate-900">
                  <ShieldCheck className="w-3.5 h-3.5 text-trust" />
                  Authenticated Submission Safeguards:
                </div>
                <p>
                  Submitted under verified identity <strong>{currentActor}</strong> ({ROLE_DEFINITIONS[currentRole as RoleType]?.title || currentRole}). Reviewer routing is calculated authoritatively by the backend based on policy.
                </p>
              </div>
            </form>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-gray-200 bg-slate-50/80 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsDrawerOpen(false)}
                disabled={submittingRequest}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
              >
                Cancel
              </button>

              <button
                type="submit"
                form="new-request-form"
                disabled={submittingRequest}
                className="px-4 py-2 bg-intelligence hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {submittingRequest ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Submitting Request...
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    Submit Request
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
