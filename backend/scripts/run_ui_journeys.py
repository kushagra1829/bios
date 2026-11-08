"""
Final product acceptance gate: six user journeys through the real Next.js UI and FastAPI backend.

Run with a Python that has Playwright installed (it drives the locally installed Chrome; no browser
download). The frontend must be served (default http://127.0.0.1:3001) and proxy to a running backend.

    <python-with-playwright> backend/scripts/run_ui_journeys.py --ui http://127.0.0.1:3001

For each journey it types the prompt into the Assistant page, clicks "Analyze Intent", captures the
actual POST /api/v1/assistant/requests response, waits for the rendered answer, takes a full-page
screenshot (with the reasoning panel expanded in a second shot), and verifies the backend evidence
independently against the source workbook with openpyxl.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "QA" / "journeys"
WB = ROOT / "data" / "source" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"

JOURNEYS = [
    ("J1", "Business sales question returns verified numbers", "What were Nubeqa sales in Germany in Q1 2026?"),
    ("J2", "New dashboard request is answered with reuse", "Build a Kerendia sales scorecard for Finland."),
    ("J3", "Dashboard request where duplicates exist gets evidence-backed consolidation",
     "I need a Hyrnuo net sales dashboard for the US, but we already have overlapping reports there."),
    ("J4", "Modification of an unowned asset is blocked", "Add forecast variance to AST-0268."),
    ("J5", "Governance question returns simplified findings at the end", "Why is AST-0268 blocked?"),
    ("J6", "No suitable asset: BUILD_NEW only after discovery and governance", "New monthly Certified Asset Share dashboard for Japan"),
]


def sheet(wb, name):
    rows = list(wb[name].iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:] if r[0] is not None]


def verify(jid, body, wb):
    rec, pres = body["recommendation"], body["presentation"]
    assets = {a["asset_id"]: a for a in sheet(wb, "Analytics_Assets")}
    owners = {o["owner_id"]: o for o in sheet(wb, "Owners")}
    akm = {}
    for r in sheet(wb, "Asset_KPI_Map"):
        akm.setdefault(r["asset_id"], set()).add(r["kpi_id"])
    checks = {}
    if jid == "J1":
        pmm = sheet(wb, "Product_Market_Monthly")
        expected = round(sum(r["net_sales_m_eur_syn"] for r in pmm if r["product_id"] == "P-NUB" and r["market_id"] == "DE"
                             and r["month"].strftime("%Y-%m") in ("2026-01", "2026-02", "2026-03")), 2)
        got = body["data_answer"]["figures"][0]["value"]
        checks = {"routed_as_data_question": body["request_types"][0] == "DATA_QUESTION",
                  "not_an_asset_action": rec["decision"] == "INFORMATIONAL",
                  f"value_matches_workbook ({expected})": abs(got - expected) < 0.011,
                  "unit_M_EUR": body["data_answer"]["unit"] == "M EUR",
                  "records_used_3": body["data_answer"]["coverage"]["records_used"] == 3}
    elif jid == "J2":
        t = rec["target_asset_ids"][0] if rec["target_asset_ids"] else None
        a = assets.get(t, {})
        checks = {"decision_REUSE": rec["decision"] == "REUSE",
                  "target_exists": bool(a),
                  "target_scope_Kerendia_FI": a.get("product_scope") == "Kerendia" and a.get("market_scope") == "FI",
                  "target_endorsed": a.get("endorsement") in ("certified", "promoted"),
                  "target_owner_active": bool(a.get("owner_id")) and owners[a["owner_id"]]["status"] == "active",
                  "target_maps_KPI-001": "KPI-001" in akm.get(t, set()),
                  "not_BUILD_NEW": rec["decision"] != "BUILD_NEW"}
    elif jid == "J3":
        pair = body["duplication"]["consolidation_eligible_pairs"]
        t = rec["target_asset_ids"][0] if rec["target_asset_ids"] else None
        a = assets.get(t, {})
        checks = {"decision_CONSOLIDATE": rec["decision"] == "CONSOLIDATE",
                  "gate_pair_present": bool(pair),
                  "pair_same_scope_in_workbook": bool(pair) and len({(assets[x]["product_scope"], assets[x]["market_scope"]) for x in pair[0]}) == 1,
                  "pair_shares_kpis": bool(pair) and bool(akm.get(pair[0][0], set()) & akm.get(pair[0][1], set())),
                  "target_owned": bool(a.get("owner_id")),
                  "approval_required": rec["human_approval_required"] is True}
    elif jid == "J4":
        checks = {"workbook_owner_empty": not assets["AST-0268"]["owner_id"],
                  "action_BLOCKED": rec["action_status"] == "BLOCKED",
                  "no_actionable_target": rec["target_asset_ids"] == [],
                  "RULE-003_blocker_shown": any(b["rule_id"] == "RULE-003" for b in pres["governance"]["blockers"])}
    elif jid == "J5":
        ga = body["governance_answer"]
        checks = {"routed_as_governance": body["request_types"][0] == "GOVERNANCE_QUESTION",
                  "answer_cites_RULE-003": "RULE-003" in ga["headline"],
                  "workbook_owner_empty": not assets["AST-0268"]["owner_id"],
                  "findings_after_answer": list(pres)[-1] == "governance",
                  "deduplicated": len({(f["rule_id"], f["asset_id"], f["message"]) for f in pres["governance"]["blockers"] + pres["governance"]["warnings"]})
                  == len(pres["governance"]["blockers"]) + len(pres["governance"]["warnings"])}
    elif jid == "J6":
        d = body["discovery"]
        searched = d["total_searched"]
        checks = {"decision_BUILD_NEW": rec["decision"] == "BUILD_NEW",
                  f"discovery_searched_all_{len(assets)}": searched == len(assets),
                  "no_exact_or_partial_candidates": not d["exact_matches"] and not d["partial_matches"],
                  "governance_agent_ran": any(t["agent_name"] == "GovernanceAgent" and t["status"] == "success" for t in body["traces"]),
                  "approval_required": rec["human_approval_required"] is True}
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:3001")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(WB, read_only=True, data_only=True)
    summary = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        for jid, title, prompt in JOURNEYS:
            page.goto(f"{args.ui}/assistant", wait_until="networkidle")
            page.fill("#prompt-input", prompt)
            with page.expect_response(lambda r: "/api/v1/assistant/requests" in r.url and r.request.method == "POST", timeout=120000) as info:
                page.get_by_role("button", name="Analyze Intent").click()
            resp = info.value
            body = resp.json()
            page.wait_for_selector("[data-testid=answer-view]", timeout=60000)
            rendered = page.inner_text("[data-testid=direct-answer]")
            page.screenshot(path=str(OUT / f"{jid}_answer.png"), full_page=True)
            page.click("[data-testid=reasoning-toggle]")
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / f"{jid}_reasoning.png"), full_page=True)
            (OUT / f"{jid}_api_response.json").write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
            checks = verify(jid, body, wb)
            checks["ui_rendered_backend_answer"] = rendered.strip() == body["presentation"]["direct_answer"].strip()
            checks["http_201"] = resp.status == 201
            summary.append({"journey": jid, "title": title, "prompt": prompt, "request_id": body["request_id"],
                            "decision": body["recommendation"]["decision"], "action_status": body["recommendation"]["action_status"],
                            "direct_answer": body["presentation"]["direct_answer"], "checks": checks, "passed": all(checks.values()),
                            "screenshots": [f"{jid}_answer.png", f"{jid}_reasoning.png"], "api_response": f"{jid}_api_response.json"})
            print(jid, "PASS" if all(checks.values()) else "FAIL", {k: v for k, v in checks.items() if not v})
        browser.close()
    (OUT / "JOURNEY_RESULTS.json").write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(), "ui": args.ui,
                                                          "journeys": summary}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
