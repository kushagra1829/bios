"use client";

import Link from "next/link";
import { useState } from "react";
import { ShieldAlert, AlertCircle, Info, ChevronDown, ChevronRight, ExternalLink, CheckCircle2, Ban, HelpCircle, Database } from "lucide-react";
import type { AssistantWorkflowResponse, FindingView } from "@/lib/types";

const ACTION_STYLE: Record<string, string> = {
  REUSE: "bg-emerald-50 text-emerald-800 border-emerald-200",
  CONSOLIDATE: "bg-blue-50 text-blue-800 border-blue-200",
  MODIFY: "bg-indigo-50 text-indigo-800 border-indigo-200",
  MIGRATE: "bg-purple-50 text-purple-800 border-purple-200",
  RETIRE: "bg-slate-100 text-slate-800 border-slate-300",
  BUILD_NEW: "bg-amber-50 text-amber-800 border-amber-200",
  NEEDS_CLARIFICATION: "bg-orange-50 text-orange-800 border-orange-200",
  INFORMATIONAL: "bg-sky-50 text-sky-800 border-sky-200",
};

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  ACTIONABLE: { label: "Can proceed", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  REQUIRES_APPROVAL: { label: "Requires human approval", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  BLOCKED: { label: "Blocked by governance", cls: "bg-red-50 text-red-800 border-red-200" },
  NEEDS_INPUT: { label: "Waiting for your input", cls: "bg-orange-50 text-orange-800 border-orange-200" },
  NOT_APPLICABLE: { label: "No action proposed", cls: "bg-slate-50 text-slate-700 border-slate-200" },
};

const RESPONSE_TITLE: Record<string, string> = {
  DATA_ANSWER: "Business data answer",
  ASSET_RECOMMENDATION: "Analytics asset recommendation",
  GOVERNANCE_ANSWER: "Governance answer",
  MIGRATION_RECOMMENDATION: "Migration recommendation",
  CLARIFICATION: "Clarification needed",
};

const EFFECT_LABEL: Record<string, string> = {
  PREVENTS_ACTION: "Prevents the action",
  REQUIRES_REVIEW: "Requires review",
  INFORMATIONAL: "Informational",
};

function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined) return "n/a";
  if (unit === "M EUR") return `${value < 0 ? "-" : ""}€${Math.abs(value).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}M`;
  if (unit === "units") return `${Math.round(value).toLocaleString("en-GB")} units`;
  if (unit === "%") return `${value.toFixed(2)}%`;
  if (unit === "weeks") return `${value.toFixed(2)} weeks`;
  return `${value} ${unit}`;
}

function FindingList({ title, items, tone, icon }: { title: string; items: FindingView[]; tone: string; icon: React.ReactNode }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!items.length) return null;
  return (
    <div className={`p-3.5 rounded-lg border text-xs space-y-2 ${tone}`}>
      <div className="font-bold flex items-center gap-1.5">
        {icon}
        {title} ({items.length})
      </div>
      <ul className="space-y-1.5">
        {items.map((f, i) => (
          <li key={i} className="leading-relaxed">
            <button type="button" onClick={() => setOpen(open === i ? null : i)} className="text-left w-full" aria-expanded={open === i}>
              <span className="font-mono font-semibold">{f.rule_id}</span>{" "}
              <span className="uppercase text-[10px] font-bold">{f.severity}</span>
              {f.asset_id ? <span className="font-mono"> · {f.asset_id}</span> : null}: {f.message}{" "}
              <span className="text-[10px] opacity-70">({EFFECT_LABEL[f.effect] || f.effect})</span>
            </button>
            {open === i && (
              <div className="mt-1 ml-3 p-2 rounded bg-white/70 border border-black/5 space-y-1">
                {f.required_action ? <div><b>Required action:</b> {f.required_action}</div> : null}
                {f.finding_ids && f.finding_ids.length ? <div className="font-mono text-[10px]">Findings: {f.finding_ids.join(", ")}</div> : null}
                {f.sources && f.sources.length > 1 ? <div className="text-[10px]">Merged {f.sources.length} backend entries for the same control.</div> : null}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AnswerView({ response }: { response: AssistantWorkflowResponse }) {
  const p = response.presentation;
  const rec = response.recommendation;
  if (!p || !rec) return null;
  const data = response.data_answer;
  const status = STATUS_STYLE[p.action_status] || STATUS_STYLE.NOT_APPLICABLE;
  const gov = p.governance;

  return (
    <div className="p-6 rounded-xl bg-white border border-gray-200 shadow-md space-y-5" data-testid="answer-view">
      {/* 1. Recommended action */}
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 pb-4">
        <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">{RESPONSE_TITLE[p.response_type] || "Answer"}</span>
        <span data-testid="recommended-action" className={`text-xs font-extrabold px-3 py-1 rounded-full uppercase tracking-wide border ${ACTION_STYLE[p.recommended_action] || ACTION_STYLE.INFORMATIONAL}`}>
          {p.recommended_action === "INFORMATIONAL" ? "Answer" : p.recommended_action.replace("_", " ")}
        </span>
        <span data-testid="action-status" className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${status.cls}`}>{status.label}</span>
        {(response.request_types || []).map((t) => (
          <span key={t} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{t.replace("_", " ")}</span>
        ))}
      </div>

      {/* 2. Direct business answer */}
      <div className="space-y-2">
        <h2 className="text-sm font-bold text-midnight-900">Direct answer</h2>
        <p data-testid="direct-answer" className="text-sm text-gray-800 leading-relaxed">{p.direct_answer}</p>
      </div>

      {/* Key figures for data answers */}
      {data && data.figures.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="key-figures">
          {data.figures.slice(0, 8).map((f, i) => (
            <div key={i} className="p-3 rounded-lg border border-gray-200 bg-slate-50">
              <div className="text-[11px] text-gray-500 leading-snug">{f.label}</div>
              <div className="text-base font-bold text-midnight-900 tabular-nums">{formatValue(f.value, f.unit)}</div>
            </div>
          ))}
        </div>
      )}
      {data && (
        <div className="text-[11px] text-gray-500 flex items-start gap-1.5">
          <Database className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>
            Source: {data.source?.sheet || "Product_Market_Monthly"} (synthetic SinceAI data, {data.coverage.dataset_period}). Unit: {data.unit || "n/a"}.
            {data.coverage.records_expected ? ` Records used: ${data.coverage.records_used} of ${data.coverage.records_expected}.` : ""}
          </span>
        </div>
      )}

      {/* 3. Why this is the right decision */}
      {p.why.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">{p.response_type === "DATA_ANSWER" ? "How this was calculated" : "Why this is the right answer"}</h3>
          <ul className="list-disc pl-5 space-y-1 text-xs text-gray-700 leading-relaxed">
            {p.why.slice(0, 8).map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {/* Matching assets */}
      {p.matching_assets.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Relevant existing assets</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {p.matching_assets.slice(0, 6).map((a, i) => {
              const id = a.asset_id || a.model_id;
              const target = rec.target_asset_ids.includes(id);
              return (
                <div key={`${id}-${i}`} className={`p-2.5 rounded-lg border text-xs ${target ? "border-emerald-300 bg-emerald-50/50" : "border-gray-200 bg-gray-50"}`}>
                  <div className="flex items-center justify-between gap-2">
                    {a.asset_id ? (
                      <Link href={`/assets/${a.asset_id}`} className="font-mono font-bold text-intelligence hover:underline inline-flex items-center gap-1">
                        {a.asset_id} <ExternalLink className="w-3 h-3" />
                      </Link>
                    ) : (
                      <span className="font-mono font-bold">{id}</span>
                    )}
                    {target && <span className="text-[10px] font-bold uppercase text-emerald-700">Recommended target</span>}
                  </div>
                  <div className="text-gray-800 font-medium">{a.asset_name || a.model_name}</div>
                  <div className="text-[10px] text-gray-500">
                    {[a.product_scope, a.market_scope || a.region_scope, a.platform, a.endorsement, a.lifecycle_status || a.recommended_path, a.owner_name ? `owner ${a.owner_name}` : a.asset_id ? "no owner" : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 4. Next steps */}
      {p.next_steps.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Recommended next steps</h3>
          <ol className="list-decimal pl-5 space-y-1 text-xs text-gray-700">
            {p.next_steps.slice(0, 6).map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}

      {/* Approval */}
      <div className="flex flex-wrap items-center gap-2 text-xs pt-2 border-t border-gray-100">
        {p.action_status === "BLOCKED" ? (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-800 font-semibold"><Ban className="w-3.5 h-3.5" /> Blocked</span>
        ) : p.human_approval_required ? (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-800 font-semibold"><ShieldAlert className="w-3.5 h-3.5" /> Human approval required</span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold"><CheckCircle2 className="w-3.5 h-3.5" /> No approval needed</span>
        )}
        <span className="text-gray-600">{p.approval_explanation}</span>
        {p.human_approval_required && p.action_status !== "BLOCKED" && (
          <Link href="/approvals" className="text-intelligence font-bold hover:underline">Open approvals queue →</Link>
        )}
      </div>
      <p className="text-[11px] text-gray-500 flex items-center gap-1"><HelpCircle className="w-3 h-3" /> {p.confidence_explanation}</p>

      {/* 5-7. Governance, always last */}
      {(gov.blockers.length > 0 || gov.warnings.length > 0 || gov.directives.length > 0) && (
        <div className="space-y-2 pt-3 border-t border-gray-200" data-testid="governance-section">
          <FindingList title="Governance Blockers" items={gov.blockers} tone="bg-red-50 border-red-200 text-red-900" icon={<ShieldAlert className="w-4 h-4" />} />
          <FindingList title="Governance Warnings & Caveats" items={gov.warnings} tone="bg-amber-50 border-amber-200 text-amber-900" icon={<AlertCircle className="w-4 h-4" />} />
          <FindingList title="Key Governance Directive" items={gov.directives} tone="bg-sky-50 border-sky-200 text-sky-900" icon={<Info className="w-4 h-4" />} />
          <p className="text-[10px] text-gray-500">
            Backend reported {gov.backend_blocker_count} blocker and {gov.backend_warning_count} warning entries; shown after removing duplicates of the same control.
            {gov.out_of_scope_count ? ` ${gov.out_of_scope_count} finding(s) on assets outside the requested scope are not blockers and are available in the reasoning panel.` : ""}
          </p>
        </div>
      )}
    </div>
  );
}

export function ReasoningToggle({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm space-y-3">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between text-xs font-bold text-gray-700 uppercase tracking-wider" aria-expanded={open} data-testid="reasoning-toggle">
        <span>View AI reasoning and evidence</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      {open && <div className="space-y-4">{children}</div>}
      {!open && <p className="text-[11px] text-gray-500">Six-agent timeline, step outputs and evidence explorer. Shows factual execution steps and evidence references only.</p>}
    </div>
  );
}
