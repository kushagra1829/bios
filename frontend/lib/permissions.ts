/**
 * BIOS Enterprise Role-Based Access Control (RBAC) & Navigation Permissions.
 * Centralized authorization rules for workspace visibility and route access.
 */
import {
  LayoutDashboard,
  Sparkles,
  BarChart3,
  ShieldAlert,
  CheckSquare,
  RefreshCw,
  FileCode2,
  Settings,
  Activity,
  Bell,
  PlugZap,
  LucideIcon,
} from "lucide-react";

export type RoleType =
  | "REQUESTER"
  | "ASSET_OWNER"
  | "DOMAIN_STEWARD"
  | "BI_GOVERNANCE_REVIEWER"
  | "BIOS_ADMIN";

export interface NavItemConfig {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  badgeColor?: string;
  allowedRoles: RoleType[];
}

export const ALL_NAV_ITEMS: NavItemConfig[] = [
  {
    id: "dashboard",
    label: "Command Center",
    href: "/dashboard",
    icon: LayoutDashboard,
    allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "assistant",
    label: "Analytics Intelligence",
    href: "/assistant",
    icon: Sparkles,
    allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "assets",
    label: "Analytics Portfolio",
    href: "/assets",
    icon: BarChart3,
    allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "governance",
    label: "Governance & Compliance",
    href: "/governance",
    icon: ShieldAlert,
    allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "alerts",
    label: "Alert Centre",
    href: "/alerts",
    icon: Bell,
    allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "approvals",
    label: "Approvals & Decisions",
    href: "/approvals",
    icon: CheckSquare,
    allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "lifecycle",
    label: "Lifecycle Management",
    href: "/lifecycle",
    icon: RefreshCw,
    allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "artifacts",
    label: "Development Studio",
    href: "/artifacts",
    icon: FileCode2,
    allowedRoles: ["DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "monitoring",
    label: "Continuous Monitoring",
    href: "/monitoring",
    icon: Activity,
    allowedRoles: ["BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"],
  },
  {
    id: "admin",
    label: "Platform Administration",
    href: "/admin",
    icon: Settings,
    allowedRoles: ["BIOS_ADMIN"],
  },
  {
    id: "integrations",
    label: "BI Integrations",
    href: "/integrations",
    icon: PlugZap,
    allowedRoles: ["BIOS_ADMIN"],
  },
];

export function getAuthorizedNavItems(role: string): NavItemConfig[] {
  const normRole = (role || "REQUESTER").toUpperCase() as RoleType;
  return ALL_NAV_ITEMS.filter((item) => item.allowedRoles.includes(normRole) && item.id !== "integrations");
}

export function isRouteAuthorized(pathname: string, role: string): boolean {
  if (!pathname || pathname === "/") return true;
  const normRole = (role || "REQUESTER").toUpperCase() as RoleType;
  
  // Find matching nav item
  const item = ALL_NAV_ITEMS.find((nav) => {
    if (nav.href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(nav.href);
  });

  if (!item) return true; // Unprotected route
  return item.allowedRoles.includes(normRole);
}

export interface RoleInfo {
  role: RoleType;
  title: string;
  scopeType: string;
  scopeDefault: string;
  color: string;
  badgeBg: string;
  badgeText: string;
}

export interface WorkspaceOption {
  role: RoleType;
  label: string;
  defaultActorId: string;
}

export const WORKSPACE_OPTIONS: WorkspaceOption[] = [
  { role: "REQUESTER", label: "Requester / Analyst", defaultActorId: "REQ-001" },
  { role: "ASSET_OWNER", label: "Asset Owner", defaultActorId: "OWN-001" },
  { role: "DOMAIN_STEWARD", label: "Domain Steward", defaultActorId: "OWN-003" },
  { role: "BI_GOVERNANCE_REVIEWER", label: "BI Governance Reviewer", defaultActorId: "REV-001" },
  { role: "BIOS_ADMIN", label: "BIOS Administrator", defaultActorId: "ADM-001" },
];

export function getWorkspaceOption(role: string): WorkspaceOption {
  const normRole = (role || "REQUESTER").toUpperCase() as RoleType;
  return WORKSPACE_OPTIONS.find((opt) => opt.role === normRole) || WORKSPACE_OPTIONS[0];
}

export const ROLE_DEFINITIONS: Record<RoleType, RoleInfo> = {
  REQUESTER: {
    role: "REQUESTER",
    title: "Requester / Analyst",
    scopeType: "Individual Scope",
    scopeDefault: "Personal Business Scope",
    color: "slate",
    badgeBg: "bg-slate-100",
    badgeText: "text-slate-800",
  },
  ASSET_OWNER: {
    role: "ASSET_OWNER",
    title: "Asset Owner",
    scopeType: "Asset Custody Scope",
    scopeDefault: "Asia Pacific (9 Assets)",
    color: "blue",
    badgeBg: "bg-blue-100",
    badgeText: "text-blue-800",
  },
  DOMAIN_STEWARD: {
    role: "DOMAIN_STEWARD",
    title: "Domain Steward",
    scopeType: "Domain Scope",
    scopeDefault: "Latin America Domain",
    color: "emerald",
    badgeBg: "bg-emerald-100",
    badgeText: "text-emerald-800",
  },
  BI_GOVERNANCE_REVIEWER: {
    role: "BI_GOVERNANCE_REVIEWER",
    title: "BI Governance Reviewer",
    scopeType: "Enterprise Scope",
    scopeDefault: "Global Fleet (360 Assets)",
    color: "amber",
    badgeBg: "bg-amber-100",
    badgeText: "text-amber-800",
  },
  BIOS_ADMIN: {
    role: "BIOS_ADMIN",
    title: "BIOS Administrator",
    scopeType: "System Admin Scope",
    scopeDefault: "Full System Infrastructure",
    color: "purple",
    badgeBg: "bg-purple-100",
    badgeText: "text-purple-800",
  },
};

