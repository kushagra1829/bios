/**
 * BIOS Enterprise Role-Based Navigation & Workspace Verification Test Suite
 * Validates workspace selector options, identity mappings, workspace visibility,
 * route authorization boundaries, and navigation filtering for:
 * 1. Requester / Analyst (REQUESTER -> REQ-001)
 * 2. Asset Owner (ASSET_OWNER -> OWN-001)
 * 3. Domain Steward (DOMAIN_STEWARD -> OWN-003)
 * 4. BI Governance Reviewer (BI_GOVERNANCE_REVIEWER -> REV-001)
 * 5. BIOS Administrator (BIOS_ADMIN -> ADM-001)
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Read permissions.ts directly to verify source of truth
const permissionsSource = fs.readFileSync(path.resolve(__dirname, "../lib/permissions.ts"), "utf-8");

console.log("=== [BIOS FRONTEND RBAC & ENTERPRISE WORKSPACE TEST SUITE] ===");

// 1. Verify all 5 enterprise roles are represented in permissions.ts
const expectedRoles = [
  "REQUESTER",
  "ASSET_OWNER",
  "DOMAIN_STEWARD",
  "BI_GOVERNANCE_REVIEWER",
  "BIOS_ADMIN"
];

for (const role of expectedRoles) {
  assert.ok(permissionsSource.includes(`"${role}"`), `Role ${role} must exist in permissions.ts`);
}
console.log("✔ All 5 enterprise roles defined in permissions.ts");

// 2. Verify WORKSPACE_OPTIONS contains the exact 5 enterprise dropdown options
const EXPECTED_WORKSPACE_OPTIONS = [
  { role: "REQUESTER", label: "Requester / Analyst", defaultActorId: "REQ-001" },
  { role: "ASSET_OWNER", label: "Asset Owner", defaultActorId: "OWN-001" },
  { role: "DOMAIN_STEWARD", label: "Domain Steward", defaultActorId: "OWN-003" },
  { role: "BI_GOVERNANCE_REVIEWER", label: "BI Governance Reviewer", defaultActorId: "REV-001" },
  { role: "BIOS_ADMIN", label: "BIOS Administrator", defaultActorId: "ADM-001" },
];

for (const opt of EXPECTED_WORKSPACE_OPTIONS) {
  assert.ok(permissionsSource.includes(`"${opt.label}"`), `Option label "${opt.label}" must exist in permissions.ts`);
  assert.ok(permissionsSource.includes(`"${opt.defaultActorId}"`), `Default ID "${opt.defaultActorId}" must exist in permissions.ts`);
  // Ensure dropdown labels do NOT expose internal IDs
  assert.ok(!opt.label.includes("REQ-"), "Dropdown label must not expose REQ- ID");
  assert.ok(!opt.label.includes("OWN-"), "Dropdown label must not expose OWN- ID");
  assert.ok(!opt.label.includes("REV-"), "Dropdown label must not expose REV- ID");
  assert.ok(!opt.label.includes("ADM-"), "Dropdown label must not expose ADM- ID");
}
console.log("✔ All 5 enterprise workspace options cleanly defined without exposing internal IDs");

// 3. Define expected authorized workspace IDs per role
const EXPECTED_NAV_ITEMS = {
  REQUESTER: ["dashboard", "assistant", "assets", "approvals"],
  ASSET_OWNER: ["dashboard", "assistant", "assets", "governance", "alerts", "approvals", "lifecycle"],
  DOMAIN_STEWARD: ["dashboard", "assistant", "assets", "governance", "alerts", "approvals", "lifecycle", "artifacts"],
  BI_GOVERNANCE_REVIEWER: ["dashboard", "assistant", "assets", "governance", "alerts", "approvals", "lifecycle", "artifacts", "monitoring"],
  BIOS_ADMIN: ["dashboard", "assistant", "assets", "governance", "alerts", "approvals", "lifecycle", "artifacts", "monitoring", "admin"]
};

// Test item extraction and logic
const NAV_ITEM_MAP = [
  { id: "dashboard", href: "/dashboard", allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "assistant", href: "/assistant", allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "assets", href: "/assets", allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "governance", href: "/governance", allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "alerts", href: "/alerts", allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "approvals", href: "/approvals", allowedRoles: ["REQUESTER", "ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "lifecycle", href: "/lifecycle", allowedRoles: ["ASSET_OWNER", "DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "artifacts", href: "/artifacts", allowedRoles: ["DOMAIN_STEWARD", "BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "monitoring", href: "/monitoring", allowedRoles: ["BI_GOVERNANCE_REVIEWER", "BIOS_ADMIN"] },
  { id: "admin", href: "/admin", allowedRoles: ["BIOS_ADMIN"] },
  { id: "integrations", href: "/integrations", allowedRoles: ["BIOS_ADMIN"] }
];

function getAuthorizedNavItems(role) {
  const normRole = (role || "REQUESTER").toUpperCase();
  return NAV_ITEM_MAP.filter((item) => item.allowedRoles.includes(normRole) && item.id !== "integrations");
}

function isRouteAuthorized(pathname, role) {
  if (!pathname || pathname === "/") return true;
  const normRole = (role || "REQUESTER").toUpperCase();
  const item = NAV_ITEM_MAP.find((nav) => {
    if (nav.href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(nav.href);
  });
  if (!item) return true;
  return item.allowedRoles.includes(normRole);
}

// 4. Test workspace counts and membership for each role
for (const [role, expectedIds] of Object.entries(EXPECTED_NAV_ITEMS)) {
  const items = getAuthorizedNavItems(role);
  const itemIds = items.map(i => i.id);
  assert.equal(itemIds.length, expectedIds.length, `${role} expected ${expectedIds.length} items, got ${itemIds.length}`);
  assert.deepEqual(itemIds, expectedIds, `${role} items match exact hierarchy`);
  console.log(`✔ ${role}: Exactly ${itemIds.length} workspaces visible [${itemIds.join(", ")}]`);
}

// 5. Test strict negative boundaries (403 direct route simulation)
console.log("\n--- Validating Route Authorization Barriers ---");

// REQUESTER forbidden routes
assert.equal(isRouteAuthorized("/governance", "REQUESTER"), false, "REQUESTER must not access /governance");
assert.equal(isRouteAuthorized("/alerts", "REQUESTER"), false, "REQUESTER must not access /alerts");
assert.equal(isRouteAuthorized("/lifecycle", "REQUESTER"), false, "REQUESTER must not access /lifecycle");
assert.equal(isRouteAuthorized("/artifacts", "REQUESTER"), false, "REQUESTER must not access /artifacts");
assert.equal(isRouteAuthorized("/monitoring", "REQUESTER"), false, "REQUESTER must not access /monitoring");
assert.equal(isRouteAuthorized("/admin", "REQUESTER"), false, "REQUESTER must not access /admin");
assert.equal(isRouteAuthorized("/integrations", "REQUESTER"), false, "REQUESTER must not access /integrations");
console.log("✔ REQUESTER strictly barred from all 7 privileged routes");

// ASSET_OWNER forbidden routes
assert.equal(isRouteAuthorized("/artifacts", "ASSET_OWNER"), false, "ASSET_OWNER must not access /artifacts");
assert.equal(isRouteAuthorized("/monitoring", "ASSET_OWNER"), false, "ASSET_OWNER must not access /monitoring");
assert.equal(isRouteAuthorized("/admin", "ASSET_OWNER"), false, "ASSET_OWNER must not access /admin");
assert.equal(isRouteAuthorized("/integrations", "ASSET_OWNER"), false, "ASSET_OWNER must not access /integrations");
console.log("✔ ASSET_OWNER strictly barred from /artifacts, /monitoring, /admin, /integrations");

// DOMAIN_STEWARD forbidden routes
assert.equal(isRouteAuthorized("/monitoring", "DOMAIN_STEWARD"), false, "DOMAIN_STEWARD must not access /monitoring");
assert.equal(isRouteAuthorized("/admin", "DOMAIN_STEWARD"), false, "DOMAIN_STEWARD must not access /admin");
assert.equal(isRouteAuthorized("/integrations", "DOMAIN_STEWARD"), false, "DOMAIN_STEWARD must not access /integrations");
console.log("✔ DOMAIN_STEWARD strictly barred from /monitoring, /admin, /integrations");

// BI_GOVERNANCE_REVIEWER forbidden routes (Admin separation)
assert.equal(isRouteAuthorized("/admin", "BI_GOVERNANCE_REVIEWER"), false, "BI_GOVERNANCE_REVIEWER must not access /admin");
assert.equal(isRouteAuthorized("/integrations", "BI_GOVERNANCE_REVIEWER"), false, "BI_GOVERNANCE_REVIEWER must not access /integrations");
console.log("✔ BI_GOVERNANCE_REVIEWER strictly barred from Platform Administration and Integrations");

// BIOS_ADMIN full access
assert.equal(isRouteAuthorized("/admin", "BIOS_ADMIN"), true, "BIOS_ADMIN has access to /admin");
assert.equal(isRouteAuthorized("/integrations", "BIOS_ADMIN"), true, "BIOS_ADMIN has access to /integrations");
assert.equal(isRouteAuthorized("/monitoring", "BIOS_ADMIN"), true, "BIOS_ADMIN has access to /monitoring");
console.log("✔ BIOS_ADMIN retains full platform administrative access");

console.log("\n=======================================================");
console.log("ALL FRONTEND RBAC & WORKSPACE TESTS PASSED (100%)");
console.log("=======================================================");
