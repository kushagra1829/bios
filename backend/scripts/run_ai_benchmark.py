"""
Run the 1,000-question benchmark against the real BIOS Assistant API and score it.

    backend\\.venv\\Scripts\\python.exe backend\\scripts\\run_ai_benchmark.py --base-url http://127.0.0.1:8001

Every question is POSTed to /api/v1/assistant/requests (no in-process shortcut). Each response is
compared with the independent expectations in docs/AI/BIOS_1000_QUESTION_BENCHMARK.json. Results go
to docs/AI/BIOS_1000_QUESTION_BENCHMARK_RESULTS.json; the Markdown report is written from them.
"""
import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "docs" / "AI" / "BIOS_1000_QUESTION_BENCHMARK.json"
RESULTS = ROOT / "docs" / "AI" / "BIOS_1000_QUESTION_BENCHMARK_RESULTS.json"
ID_PATTERN = re.compile(r"\b(?:AST-\d{4}|SM-\d{3}|KPI-\d{3}|OWN-\d{3})\b")
CONSEQUENTIAL = {"MODIFY", "CONSOLIDATE", "MIGRATE", "RETIRE", "BUILD_NEW"}
TOL = 0.011


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= max(TOL, abs(float(b)) * 1e-6)


def score(q, r, known_ids, unowned):
    exp = q["expected"]
    checks = {}
    rec = r["recommendation"]
    intent = r["intent"]
    types = r.get("request_types") or []
    decision = rec["decision"]
    data = r.get("data_answer")
    gov = r.get("governance_answer")
    mig = r.get("migration_answer")
    pres = r.get("presentation") or {}

    checks["intent"] = bool(types) and types[0] == q["expected_intent"]
    if exp.get("secondary_intent"):
        checks["intent"] = checks["intent"] and exp["secondary_intent"] in types
    if isinstance(q["product"], list):
        checks["product"] = all(p in intent["products"] for p in q["product"])

    if data is not None and q["expected_intent"] == "DATA_QUESTION":
        allowed = exp.get("data_status", "").split("|") if exp.get("data_status") else None
        if allowed:
            checks["clarification" if any(s in ("NEEDS_CLARIFICATION", "UNSUPPORTED", "NO_DATA") for s in allowed) else "data_status"] = data["status"] in allowed
        if "market_ids" in exp and data["status"] in ("ANSWERED", "PARTIAL"):
            checks["geography"] = sorted(data["markets"]) == exp["market_ids"]
        if exp.get("period_start") and data["status"] in ("ANSWERED", "PARTIAL"):
            checks["date_filter"] = data["period_start"] == exp["period_start"] and data["period_end"] == exp["period_end"]
        if exp.get("measure_field") and data["status"] in ("ANSWERED", "PARTIAL"):
            checks["kpi"] = data["measure_field"] == exp["measure_field"] or exp.get("operation") == "FORECAST_VS_ACTUAL"
        if exp.get("values") and data["status"] in ("ANSWERED", "PARTIAL"):
            got = [f["value"] for f in data["figures"]]
            if exp.get("values_match") == "all":
                checks["numeric"] = all(any(close(g, e) for g in got) for e in exp["values"])
            else:
                checks["numeric"] = bool(got) and close(got[0], exp["values"][0])
            if "records_used" in exp:
                checks["coverage"] = data["coverage"]["records_used"] == exp["records_used"]
            if exp.get("leader"):
                checks["numeric"] = checks["numeric"] and exp["leader"] in data["headline"]
        unsupported_expected = exp.get("no_figures") or exp.get("data_status") in ("NO_DATA", "UNSUPPORTED")
        if unsupported_expected:
            checks["no_unsupported_claim"] = not any(f.get("value") is not None for f in data["figures"])
    elif q["expected_intent"] == "DATA_QUESTION" and exp.get("data_status"):
        checks["data_status"] = False
    if exp.get("must_not_decision"):
        checks["decision_guard"] = decision not in exp["must_not_decision"]
    if exp.get("acceptable_decisions"):
        key = {"ASSET_DISCOVERY": "reuse", "DUPLICATION_ASSESSMENT": "duplication", "ASSET_DIRECTED_ACTION": "duplication"}.get(q["expected_workflow"], "decision")
        checks[key] = decision in exp["acceptable_decisions"]
    if exp.get("eligible_pairs") and decision == "CONSOLIDATE":
        pair_ids = {a for p in exp["eligible_pairs"] for a in p}
        checks["duplication"] = checks.get("duplication", True) and set(rec["target_asset_ids"]) <= pair_ids
    if exp.get("action_status"):
        checks["governance_consistency"] = rec.get("action_status") == exp["action_status"]
    if exp.get("blocker_rules"):
        text = " ".join(rec["blockers"])
        checks["governance_consistency"] = checks.get("governance_consistency", True) and all(rule in text for rule in exp["blocker_rules"])
    forbidden = set(exp.get("forbidden_targets") or [])
    # Governance consistency on every asset decision: no unowned asset may be an actionable target.
    if decision in CONSEQUENTIAL | {"REUSE"}:
        bad = set(rec["target_asset_ids"]) & (forbidden | unowned)
        checks["target_governance"] = not bad
    if exp.get("approval_required") is not None and decision in CONSEQUENTIAL:
        checks["approval"] = rec["human_approval_required"] is exp["approval_required"]
    if decision in CONSEQUENTIAL:
        checks["approval_enforced"] = rec["human_approval_required"] is True
    if exp.get("security_flag"):
        checks["security"] = any(a["category"] == "security_override_attempt" for a in intent["ambiguities"])
    if exp.get("governance_kind"):
        checks["governance_answer"] = gov is not None and gov["question_kind"] == exp["governance_kind"]
        if gov is not None:
            if "total_matching" in exp:
                checks["governance_answer"] = checks["governance_answer"] and gov["total_matching"] == exp["total_matching"]
            if "min_total_matching" in exp:
                checks["governance_answer"] = checks["governance_answer"] and gov["total_matching"] >= exp["min_total_matching"]
            for needle in exp.get("headline_contains", []):
                checks["governance_answer"] = checks["governance_answer"] and needle.lower() in (gov["headline"] + " ".join(gov["explanation"])).lower()
            if exp.get("kpi_id"):
                checks["kpi"] = bool(gov["kpis"]) and any(k["kpi_id"] == exp["kpi_id"] for k in gov["kpis"]) and exp["kpi_id"] in gov["headline"]
            if exp.get("kpi_approval_status"):
                row = next((k for k in gov["kpis"] if k["kpi_id"] == exp.get("kpi_id")), None)
                checks["kpi"] = checks.get("kpi", True) and row is not None and row["approval_status"] == exp["kpi_approval_status"]
            if exp.get("model_id"):
                checks["governance_answer"] = checks["governance_answer"] and bool(gov["assets"]) and gov["assets"][0].get("model_id") == exp["model_id"]
            if "lineage_upstream" in exp:
                checks["governance_answer"] = checks["governance_answer"] and bool(gov["assets"]) and sorted(gov["assets"][0].get("lineage_upstream", [])) == exp["lineage_upstream"]
            if exp.get("asset_ids"):
                checks["asset_discovery"] = all(a["asset_id"] in exp["asset_ids"] for a in gov["assets"]) and bool(gov["assets"])
    if exp.get("governance_status"):
        checks["governance_answer"] = gov is not None and gov["status"] == exp["governance_status"]
    if exp.get("targets_any_of"):
        checks["asset_discovery"] = any(t in exp["targets_any_of"] for t in rec["target_asset_ids"])
    if "migration_total" in exp:
        checks["migration"] = mig is not None and mig["total_matching"] == exp["migration_total"]
    if "migration_groups" in exp:
        got = {k: len(v) for k, v in (mig or {}).get("groups", {}).items()}
        checks["migration"] = checks.get("migration", True) and mig is not None and all(got.get(k, 0) == v for k, v in exp["migration_groups"].items())

    # Hallucination: every ID the business-facing answer cites must exist in the workbook.
    cited = set(ID_PATTERN.findall(json.dumps({"rec": rec, "pres": pres})))
    phantoms = sorted(cited - known_ids)
    checks["no_hallucination"] = not phantoms
    return checks, phantoms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    known = set(bench["known_ids"])
    import openpyxl  # unowned set from the workbook, independent of BIOS
    wb = openpyxl.load_workbook(ROOT / bench["source"], read_only=True, data_only=True)
    rows = list(wb["Analytics_Assets"].iter_rows(values_only=True))
    head = rows[0]
    unowned = {r[head.index("asset_id")] for r in rows[1:] if r[0] and not r[head.index("owner_id")]}

    questions = bench["questions"][: args.limit or None]
    results = []
    client = httpx.Client(base_url=args.base_url, timeout=120)
    t0 = time.time()
    for i, q in enumerate(questions, 1):
        start = time.perf_counter()
        try:
            resp = client.post("/api/v1/assistant/requests", json={"prompt": q["question"]})
            ok = resp.status_code == 201
            body = resp.json() if ok else {"detail": resp.text[:300]}
        except Exception as exc:  # recorded as a failure, never skipped
            ok, body = False, {"detail": str(exc)}
        ms = round((time.perf_counter() - start) * 1000, 1)
        if ok:
            checks, phantoms = score(q, body, known, unowned)
        else:
            checks, phantoms = {"api_ok": False}, []
        results.append({
            "question_id": q["question_id"], "category": q["category"], "ground_truth_status": q["ground_truth_status"],
            "question": q["question"], "request_id": body.get("request_id"), "latency_ms": ms,
            "request_types": body.get("request_types"), "decision": (body.get("recommendation") or {}).get("decision"),
            "action_status": (body.get("recommendation") or {}).get("action_status"),
            "data_status": (body.get("data_answer") or {}).get("status"), "headline": (body.get("presentation") or {}).get("direct_answer", "")[:300],
            "checks": checks, "passed": all(checks.values()), "phantoms": phantoms, "regression_case": q.get("regression_case"),
        })
        if i % 100 == 0:
            print(f"{i} done, {sum(r['passed'] for r in results)} passed, {time.time() - t0:.0f}s", flush=True)

    dims = defaultdict(lambda: [0, 0])
    cats = defaultdict(lambda: [0, 0])
    gts = defaultdict(lambda: [0, 0])
    for r in results:
        cats[r["category"]][1] += 1
        cats[r["category"]][0] += r["passed"]
        gts[r["ground_truth_status"]][1] += 1
        gts[r["ground_truth_status"]][0] += r["passed"]
        for k, v in r["checks"].items():
            dims[k][1] += 1
            dims[k][0] += bool(v)
    summary = {
        "base_url": args.base_url,
        "questions": len(results),
        "fully_passed": sum(r["passed"] for r in results),
        "by_category": {k: {"passed": v[0], "total": v[1], "pct": round(100 * v[0] / v[1], 1)} for k, v in sorted(cats.items())},
        "by_dimension": {k: {"passed": v[0], "total": v[1], "pct": round(100 * v[0] / v[1], 1)} for k, v in sorted(dims.items())},
        "by_ground_truth": {k: {"passed": v[0], "total": v[1], "pct": round(100 * v[0] / v[1], 1)} for k, v in sorted(gts.items())},
        "regression_cases": [{"case": r["regression_case"], "question": r["question"], "passed": r["passed"], "decision": r["decision"],
                              "checks": r["checks"]} for r in sorted((r for r in results if r["regression_case"]), key=lambda r: r["regression_case"])],
        "hallucinated_ids": sorted({p for r in results for p in r["phantoms"]}),
        "latency_ms": {"mean": round(sum(r["latency_ms"] for r in results) / len(results), 1),
                       "p95": sorted(r["latency_ms"] for r in results)[int(len(results) * 0.95) - 1]},
        "elapsed_s": round(time.time() - t0, 1),
    }
    RESULTS.write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1)[:4000])


if __name__ == "__main__":
    main()
