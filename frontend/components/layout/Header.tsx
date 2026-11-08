"use client";

import { useState, useEffect } from "react";
import { Database, Briefcase, ChevronDown, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { WORKSPACE_OPTIONS, RoleType } from "@/lib/permissions";

interface HeaderProps {
  currentRole: string;
  onRoleChange: (role: string) => void;
  isTransitioning?: boolean;
}

export default function Header({ currentRole, onRoleChange, isTransitioning = false }: HeaderProps) {
  const [healthStatus, setHealthStatus] = useState<string>("checking");

  useEffect(() => {
    api
      .getHealth()
      .then((res) => {
        setHealthStatus(res.status === "healthy" ? "healthy" : "warning");
      })
      .catch(() => {
        setHealthStatus("offline");
      });
  }, []);

  return (
    <header className="h-16 bg-white border-b border-gray-200 px-6 flex items-center justify-between z-10 shrink-0">
      {/* Left: Environment & Enterprise Data Context */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-xs text-blue-900 font-medium">
          <Database className="w-3.5 h-3.5 text-intelligence" />
          <span className="font-semibold">Dataset:</span>
          <span>Synthetic Challenge Data Pack (SHA: 7d0187...)</span>
        </div>

        {/* Only show warning/offline if service is actually disrupted */}
        {healthStatus !== "healthy" && healthStatus !== "checking" && (
          <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-2 h-2 rounded-full bg-critical" />
            <span className="capitalize">
              {healthStatus === "warning" ? "Service Disrupted" : "Backend Disconnected"}
            </span>
          </div>
        )}
      </div>

      {/* Right: One Enterprise Role-Based Workspace Dropdown */}
      <div className="flex items-center gap-3">
        {currentRole === "ASSET_OWNER" && (
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 border border-blue-200 text-blue-900">
            <span className="font-semibold">Asset Custody:</span>
            <span>Nina Garcia (OWN-001)</span>
          </div>
        )}

        <div className="flex items-center bg-slate-50 border border-slate-200 rounded-lg py-1 px-3 shadow-2xs">
          <label htmlFor="workspace-dropdown" className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 mr-2 select-none">
            <Briefcase className="w-3.5 h-3.5 text-intelligence" />
            <span>Workspace:</span>
          </label>

          <div className="relative">
            <select
              id="workspace-dropdown"
              value={currentRole}
              onChange={(e) => onRoleChange(e.target.value)}
              disabled={isTransitioning}
              className="appearance-none bg-white border border-gray-300 hover:border-gray-400 rounded-md pl-2.5 pr-7 py-1 text-xs text-gray-900 font-semibold focus:outline-none focus:ring-1 focus:ring-intelligence cursor-pointer disabled:opacity-50 transition-colors"
              title="Select authorized organizational workspace role"
            >
              {WORKSPACE_OPTIONS.map((opt) => (
                <option key={opt.role} value={opt.role}>
                  {opt.label}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-gray-400">
              {isTransitioning ? (
                <Loader2 className="w-3 h-3 animate-spin text-intelligence" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
