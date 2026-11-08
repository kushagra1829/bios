"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Lock, RefreshCw } from "lucide-react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { setApiAuth } from "@/lib/api";
import { isRouteAuthorized, ROLE_DEFINITIONS, RoleType, getWorkspaceOption } from "@/lib/permissions";

interface AuthContextType {
  actorId: string;
  actorRole: string;
  currentActor: string;
  currentRole: string;
  isTransitioning: boolean;
  setActorRole: (role: string) => void;
  setActorId: (id: string) => void;
}

const AuthContext = createContext<AuthContextType>({
  actorId: "REV-001",
  actorRole: "BI_GOVERNANCE_REVIEWER",
  currentActor: "REV-001",
  currentRole: "BI_GOVERNANCE_REVIEWER",
  isTransitioning: false,
  setActorRole: () => {},
  setActorId: () => {},
});

export const useAuth = () => useContext(AuthContext);

export default function Shell({ children }: { children: ReactNode }) {
  const [actorRole, setActorRoleState] = useState<string>("BI_GOVERNANCE_REVIEWER");
  const [actorId, setActorIdState] = useState<string>("REV-001");
  const [isTransitioning, setIsTransitioning] = useState<boolean>(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    // Read from session storage if present
    if (typeof window !== "undefined") {
      const savedRole = sessionStorage.getItem("bios_actor_role") || "BI_GOVERNANCE_REVIEWER";
      const opt = getWorkspaceOption(savedRole);
      const savedId = sessionStorage.getItem("bios_actor_id") || opt.defaultActorId;
      setActorRoleState(opt.role);
      setActorIdState(savedId);
      setApiAuth(savedId, opt.role);
    }
  }, []);

  const handleWorkspaceChange = (newRole: string) => {
    setIsTransitioning(true);
    const opt = getWorkspaceOption(newRole);
    setActorRoleState(opt.role);
    setActorIdState(opt.defaultActorId);

    if (typeof window !== "undefined") {
      sessionStorage.setItem("bios_actor_role", opt.role);
      sessionStorage.setItem("bios_actor_id", opt.defaultActorId);
    }
    setApiAuth(opt.defaultActorId, opt.role);

    // If current route is not authorized for the newly selected workspace, redirect to /dashboard
    if (!isRouteAuthorized(pathname || "", opt.role)) {
      router.push("/dashboard");
    }

    // Brief smooth transition to allow components to re-render with fresh context
    setTimeout(() => {
      setIsTransitioning(false);
    }, 200);
  };

  const handleActorIdChange = (id: string) => {
    setActorIdState(id);
    if (typeof window !== "undefined") sessionStorage.setItem("bios_actor_id", id);
    setApiAuth(id, actorRole);
  };

  const isAuthorized = isRouteAuthorized(pathname || "", actorRole);
  const roleDef = ROLE_DEFINITIONS[actorRole as RoleType] || ROLE_DEFINITIONS.REQUESTER;

  return (
    <AuthContext.Provider
      value={{
        actorId,
        actorRole,
        currentActor: actorId,
        currentRole: actorRole,
        isTransitioning,
        setActorRole: handleWorkspaceChange,
        setActorId: handleActorIdChange,
      }}
    >
      <div className="flex h-screen w-screen overflow-hidden bg-cloud">
        <Sidebar />
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
          <Header
            currentRole={actorRole}
            onRoleChange={handleWorkspaceChange}
            isTransitioning={isTransitioning}
          />
          <main className="flex-1 overflow-y-auto p-6 relative">
            {isTransitioning ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-intelligence/10 text-intelligence flex items-center justify-center animate-spin">
                  <RefreshCw className="w-6 h-6" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-bold text-midnight-900">
                    Switching Workspace to {roleDef.title}...
                  </p>
                  <p className="text-xs text-gray-500">
                    Applying authorized scope boundaries and role-specific governance telemetry.
                  </p>
                </div>
              </div>
            ) : !isAuthorized ? (
              <div className="max-w-xl mx-auto my-12 p-8 bg-white border border-rose-200 rounded-2xl shadow-sm space-y-5 text-center">
                <div className="w-14 h-14 bg-rose-50 text-rose-600 rounded-2xl flex items-center justify-center mx-auto border border-rose-100">
                  <Lock className="w-7 h-7" />
                </div>
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                    403 Forbidden · Workspace Restricted
                  </span>
                  <h2 className="text-xl font-extrabold text-midnight-900 mt-3">
                    Unauthorized Workspace Access
                  </h2>
                  <p className="text-sm text-gray-500 mt-2">
                    Your current assigned workspace role ({roleDef.title}) does not have access permissions for this workspace.
                    BIOS enforces strict organizational separation of duties.
                  </p>
                </div>

                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-left text-xs space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Active Workspace:</span>
                    <span className="font-bold text-gray-900">{roleDef.title}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Organizational Scope:</span>
                    <span className="font-medium text-gray-700">{roleDef.scopeDefault}</span>
                  </div>
                </div>

                <div className="pt-2 flex justify-center gap-3">
                  <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-midnight-900 text-white text-xs font-bold hover:bg-midnight-800 transition-colors shadow-sm"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    Return to Command Center
                  </Link>
                </div>
              </div>
            ) : (
              children
            )}
          </main>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
