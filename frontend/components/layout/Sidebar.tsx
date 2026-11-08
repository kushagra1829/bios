"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layers, ShieldCheck, UserCheck } from "lucide-react";
import { useAuth } from "./Shell";
import { getAuthorizedNavItems, ROLE_DEFINITIONS, RoleType } from "@/lib/permissions";

export default function Sidebar() {
  const pathname = usePathname();
  const { actorRole, actorId } = useAuth();

  // Get strictly authorized workspaces for current organizational role
  const authorizedItems = getAuthorizedNavItems(actorRole);
  const roleDef = ROLE_DEFINITIONS[actorRole as RoleType] || ROLE_DEFINITIONS.REQUESTER;

  return (
    <aside className="w-64 bg-midnight-900 text-white flex flex-col shrink-0 border-r border-midnight-800 select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-6 gap-3 border-b border-midnight-800 bg-midnight-950/40">
        <div className="w-9 h-9 rounded-lg bg-intelligence flex items-center justify-center font-bold text-lg tracking-wider text-white shadow-md shadow-intelligence/30">
          <Layers className="w-5 h-5 text-white" />
        </div>
        <div>
          <span className="font-bold text-lg tracking-tight text-white">BIOS</span>
          <p className="text-[11px] text-midnight-300 font-medium">Enterprise BI Governance</p>
        </div>
      </div>

      {/* Role & Authorized Scope Badge */}
      <div className="p-3 mx-3 my-3 rounded-xl bg-midnight-950/60 border border-midnight-800">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] uppercase font-bold tracking-wider text-midnight-400">
            Active Workspace
          </span>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-midnight-800 text-intelligence-300 border border-midnight-700">
            {roleDef.scopeType}
          </span>
        </div>
        <div className="text-xs font-bold text-white truncate flex items-center gap-1.5">
          <UserCheck className="w-3.5 h-3.5 text-trust shrink-0" />
          <span className="truncate">{roleDef.title}</span>
        </div>
        <div className="mt-1.5 pt-1.5 border-t border-midnight-800/80 flex items-center justify-between text-[11px]">
          <span className="text-midnight-400">Scope:</span>
          <span className="text-midnight-200 font-medium truncate max-w-[140px]" title={roleDef.scopeDefault}>
            {roleDef.scopeDefault}
          </span>
        </div>
      </div>

      {/* Navigation List — Render ONLY Authorized Workspaces */}
      <nav className="flex-1 py-1 px-3 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[10px] font-bold text-midnight-400 uppercase tracking-wider flex items-center justify-between">
          <span>Authorized Workspaces</span>
          <span className="text-[10px] font-normal text-midnight-500">
            {authorizedItems.length} accessible
          </span>
        </div>

        {authorizedItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/dashboard" && pathname?.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-all group ${
                isActive
                  ? "bg-intelligence text-white shadow-sm shadow-intelligence/40 font-semibold"
                  : "text-midnight-200 hover:text-white hover:bg-midnight-800/60"
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-4 h-4 transition-transform group-hover:scale-110 ${isActive ? "text-white" : "text-midnight-300"}`} />
                <span>{item.label}</span>
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Enterprise Platform Footer */}
      <div className="px-5 py-4 border-t border-midnight-800 bg-midnight-950/40 text-[11px] text-midnight-400 flex items-center justify-between">
        <span>BIOS Enterprise</span>
        <span className="font-mono text-midnight-300">v1.0</span>
      </div>
    </aside>
  );
}
