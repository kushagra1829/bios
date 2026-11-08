"""
Re-run the failed live request (REQ-20261107181530-C774DB) and related Nubeqa Germany prompts through
the real frontend, against an LLM-assisted backend, and check that the rendered UI, the API response
and governance agree. Run with a Python that has Playwright (drives installed Chrome).

    <python-with-playwright> backend/scripts/run_ui_nubeqa_verification.py --ui http://127.0.0.1:3002
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "QA" / "live_llm_nubeqa"
PROMPTS = [
    ("N1", "check nubeqa sales in germany"),
    ("N2", "I need a scoreboard for Nubeqa sales in Germany."),
    ("N3", "Consolidate the Nubeqa Germany dashboards into AST-0268."),
    ("N4", "Can I reuse AST-0157 for Nubeqa sales in Germany?"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:3002")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(ROOT / "data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx", read_only=True, data_only=True)
    rows = list(wb["Analytics_Assets"].iter_rows(values_only=True))
    h = rows[0]
    assets = {r[0]: dict(zip(h, r)) for r in rows[1:] if r[0]}
    akm = {}
    for r in list(wb["Asset_KPI_Map"].iter_rows(values_only=True))[1:]:
        akm.setdefault(r[0], set()).add(r[1])
    unowned = {a for a, v in assets.items() if not v["owner_id"]}
    summary = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        for nid, prompt in PROMPTS:
            page.goto(f"{args.ui}/assistant", wait_until="networkidle")
            page.fill("#prompt-input", prompt)
            with page.expect_response(lambda r: "/api/v1/assistant/requests" in r.url and r.request.method == "POST", timeout=600000) as info:
                page.get_by_role("button", name="Analyze Intent").click()
            body = info.value.json()
            page.wait_for_selector("[data-testid=answer-view]", timeout=120000)
            ui_action = page.inner_text("[data-testid=recommended-action]").strip()
            ui_status = page.inner_text("[data-testid=action-status]").strip()
            ui_answer = page.inner_text("[data-testid=direct-answer]").strip()
            page.screenshot(path=str(OUT / f"{nid}_answer.png"), full_page=True)
            page.click("[data-testid=reasoning-toggle]")
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / f"{nid}_reasoning.png"), full_page=True)
            (OUT / f"{nid}_api_response.json").write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
            rec = body["recommendation"]
            modes = {t["agent_name"]: json.loads(t["execution_metadata_json"] or "{}").get("execution_mode") for t in body["traces"]}
            targets = rec["target_asset_ids"]
            checks = {
                "llm_assisted_steps_ran": any(m == "LLM_ASSISTED" for m in modes.values()),
                "no_unowned_target": not set(targets) & unowned,
                "blocked_has_no_target": rec["action_status"] != "BLOCKED" or not targets,
                "ui_answer_matches_api": ui_answer == body["presentation"]["direct_answer"].strip(),
                "ui_status_matches_api": {"ACTIONABLE": "Can proceed", "REQUIRES_APPROVAL": "Requires human approval", "BLOCKED": "Blocked by governance",
                                          "NEEDS_INPUT": "Waiting for your input", "NOT_APPLICABLE": "No action proposed"}[rec["action_status"]] == ui_status,
                "no_actionable_consolidation_into_blocked_asset": not (rec["decision"] == "CONSOLIDATE" and rec["action_status"] != "BLOCKED" and set(targets) & unowned),
                "targets_have_kpi_or_scope_evidence": all(
                    assets[t]["product_scope"] == "Nubeqa" and assets[t]["market_scope"] == "DE" for t in targets) if nid != "N1" else True,
                "validated": bool(rec.get("validation_notes")),
            }
            summary.append({"id": nid, "prompt": prompt, "request_id": body["request_id"], "decision": rec["decision"],
                            "action_status": rec["action_status"], "targets": targets,
                            "ineligible": [t["asset_id"] for t in rec["ineligible_targets"]], "ui_action": ui_action, "ui_status": ui_status,
                            "direct_answer": ui_answer, "execution_modes": modes, "target_kpis": {t: sorted(akm.get(t, [])) for t in targets},
                            "checks": checks, "passed": all(checks.values())})
            print(nid, rec["decision"], rec["action_status"], targets, "PASS" if all(checks.values()) else f"FAIL {[k for k, v in checks.items() if not v]}", flush=True)
        browser.close()
    (OUT / "RESULTS.json").write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(), "ui": args.ui, "results": summary},
                                                 indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
