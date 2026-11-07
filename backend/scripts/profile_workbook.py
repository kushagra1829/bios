"""
BIOS - Bayer Pharmaceuticals Builder Data Pack Profiling Script
Inspects all 24 sheets, columns, types, nulls, duplicates, PKs, FKs, distributions,
and data quality issues. Outputs detailed profiling summary and JSON report.
"""

import io
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, date
import openpyxl

WORKBOOK_PATH = os.path.join("data", "source", "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx")
OUTPUT_JSON_PATH = os.path.join("backend", "scripts", "profiling_output.json")


def infer_type(values):
    types = set()
    for v in values:
        if v is None:
            continue
        if isinstance(v, bool):
            types.add("BOOLEAN")
        elif isinstance(v, int):
            types.add("INTEGER")
        elif isinstance(v, float):
            if v.is_integer():
                types.add("INTEGER")
            else:
                types.add("FLOAT")
        elif isinstance(v, (datetime, date)):
            types.add("DATETIME")
        else:
            types.add("VARCHAR")
    if not types:
        return "UNKNOWN"
    if types == {"INTEGER"}:
        return "INTEGER"
    if types in ({"FLOAT"}, {"INTEGER", "FLOAT"}):
        return "FLOAT"
    if types == {"BOOLEAN"}:
        return "BOOLEAN"
    if types == {"DATETIME"}:
        return "DATETIME"
    return "VARCHAR"


def profile_sheet(ws, sheet_name):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {
            "name": sheet_name,
            "row_count": 0,
            "col_count": 0,
            "headers": [],
            "columns": {},
            "duplicate_rows": 0,
            "candidate_pk": None,
        }

    # First row is headers
    raw_headers = rows[0]
    headers = [str(c).strip() if c is not None else f"Unnamed_{i}" for i, c in enumerate(raw_headers)]
    data_rows = rows[1:]

    # Remove completely empty trailing rows if any
    data_rows = [r for r in data_rows if any(c is not None and str(c).strip() != "" for c in r)]
    row_count = len(data_rows)
    col_count = len(headers)

    # Check exact row duplicates
    row_tuples = [tuple(r[:col_count]) for r in data_rows]
    duplicate_rows = len(row_tuples) - len(set(row_tuples))

    columns_profile = {}
    for col_idx, col_name in enumerate(headers):
        vals = [r[col_idx] if col_idx < len(r) else None for r in data_rows]
        non_null_vals = [v for v in vals if v is not None and str(v).strip() != ""]
        missing_count = row_count - len(non_null_vals)
        missing_pct = round((missing_count / row_count * 100), 2) if row_count > 0 else 0.0
        distinct_count = len(set(non_null_vals))
        inferred = infer_type(non_null_vals)

        # Categorical / distribution check
        distribution = {}
        if distinct_count <= 25 and row_count > 0:
            val_counts = Counter(str(v) for v in non_null_vals)
            distribution = {k: {"count": c, "pct": round(c / row_count * 100, 2)}
                            for k, c in val_counts.most_common(15)}

        # Min / max for numbers and dates
        val_min = None
        val_max = None
        if inferred in ("INTEGER", "FLOAT") and non_null_vals:
            numeric_vals = [float(v) for v in non_null_vals if isinstance(v, (int, float))]
            if numeric_vals:
                val_min = min(numeric_vals)
                val_max = max(numeric_vals)
        elif inferred == "DATETIME" and non_null_vals:
            dt_vals = [v.isoformat() if hasattr(v, "isoformat") else str(v) for v in non_null_vals]
            if dt_vals:
                val_min = min(dt_vals)
                val_max = max(dt_vals)

        is_unique = (distinct_count == row_count) and (missing_count == 0) and row_count > 0

        sample_vals = [str(v) for v in non_null_vals[:4]]

        columns_profile[col_name] = {
            "inferred_type": inferred,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "distinct_count": distinct_count,
            "is_unique": is_unique,
            "val_min": val_min,
            "val_max": val_max,
            "sample_values": sample_vals,
            "distribution": distribution,
        }

    # Find candidate PK: single unique column first
    candidate_pk = None
    for c_name, c_info in columns_profile.items():
        if c_info["is_unique"]:
            candidate_pk = [c_name]
            break

    # If no single PK, test pairs of columns with 0 nulls
    if candidate_pk is None and row_count > 0:
        candidate_cols = [c for c, inf in columns_profile.items() if inf["missing_count"] == 0]
        found = False
        for i in range(len(candidate_cols)):
            for j in range(i + 1, len(candidate_cols)):
                c1, c2 = candidate_cols[i], candidate_cols[j]
                idx1 = headers.index(c1)
                idx2 = headers.index(c2)
                pairs = [(r[idx1], r[idx2]) for r in data_rows]
                if len(set(pairs)) == row_count:
                    candidate_pk = [c1, c2]
                    found = True
                    break
            if found:
                break

    # If still none and has 3 cols, test triplet
    if candidate_pk is None and row_count > 0 and len(candidate_cols) >= 3:
        for i in range(len(candidate_cols)):
            for j in range(i + 1, len(candidate_cols)):
                for k in range(j + 1, len(candidate_cols)):
                    c1, c2, c3 = candidate_cols[i], candidate_cols[j], candidate_cols[k]
                    idx1 = headers.index(c1)
                    idx2 = headers.index(c2)
                    idx3 = headers.index(c3)
                    triplets = [(r[idx1], r[idx2], r[idx3]) for r in data_rows]
                    if len(set(triplets)) == row_count:
                        candidate_pk = [c1, c2, c3]
                        break
                if candidate_pk:
                    break
            if candidate_pk:
                break

    return {
        "name": sheet_name,
        "row_count": row_count,
        "col_count": col_count,
        "headers": headers,
        "columns": columns_profile,
        "duplicate_rows": duplicate_rows,
        "candidate_pk": candidate_pk,
        "raw_records": [dict(zip(headers, r[:col_count])) for r in data_rows]
    }


def main():
    print(f"Loading workbook from {WORKBOOK_PATH}...")
    wb = openpyxl.load_workbook(WORKBOOK_PATH, data_only=True)
    print(f"Worksheets found ({len(wb.sheetnames)}): {wb.sheetnames}")

    sheets_profile = {}
    for s_name in wb.sheetnames:
        prof = profile_sheet(wb[s_name], s_name)
        sheets_profile[s_name] = prof
        pk_str = ", ".join(prof["candidate_pk"]) if prof["candidate_pk"] else "NONE"
        print(f"Sheet: {s_name:24} | Rows: {prof['row_count']:5} | Cols: {prof['col_count']:2} | PK: [{pk_str}] | Duplicates: {prof['duplicate_rows']}")

    # Cross-sheet foreign key verification
    records = {k: v["raw_records"] for k, v in sheets_profile.items()}

    fk_checks = [
        # (Child Table, FK Column, Parent Table, PK Column)
        ("Semantic_Models", "workspace_id", "Workspaces", "workspace_id"),
        ("Semantic_Models", "owner_id", "Owners", "owner_id"),
        ("Analytics_Assets", "workspace_id", "Workspaces", "workspace_id"),
        ("Analytics_Assets", "model_id", "Semantic_Models", "model_id"),
        ("Analytics_Assets", "owner_id", "Owners", "owner_id"),
        ("Asset_KPI_Map", "asset_id", "Analytics_Assets", "asset_id"),
        ("Asset_KPI_Map", "kpi_id", "KPI_Catalog", "kpi_id"),
        ("Asset_Usage", "asset_id", "Analytics_Assets", "asset_id"),
        ("Governance_Signals", "asset_id", "Analytics_Assets", "asset_id"),
        ("Migration_Backlog", "source_asset_id", "Analytics_Assets", "asset_id"),
        ("Migration_Backlog", "candidate_target_model_id", "Semantic_Models", "model_id"),
        ("KPI_Catalog", "owner_id", "Owners", "owner_id"),
        ("Product_Market_Monthly", "product_id", "Products", "product_id"),
        ("Product_Market_Monthly", "market_id", "Markets", "market_id"),
        ("Launch_Milestones", "product_id", "Products", "product_id"),
        ("Launch_Milestones", "market_id", "Markets", "market_id"),
        ("Market_Access", "product_id", "Products", "product_id"),
        ("Market_Access", "market_id", "Markets", "market_id"),
        ("Supply_Operations", "product_id", "Products", "product_id"),
        ("Supply_Operations", "market_id", "Markets", "market_id"),
    ]

    print("\n--- FOREIGN KEY VERIFICATION RESULTS ---")
    fk_results = []
    for child_t, fk_col, parent_t, pk_col in fk_checks:
        parent_pks = set(r[pk_col] for r in records[parent_t] if r.get(pk_col) is not None)
        child_rows = records[child_t]
        total_child = len(child_rows)
        null_count = 0
        valid_count = 0
        invalid_vals = set()

        for cr in child_rows:
            val = cr.get(fk_col)
            if val is None or str(val).strip() == "":
                null_count += 1
            elif val in parent_pks:
                valid_count += 1
            else:
                invalid_vals.add(str(val))

        status = "CONFIRMED_STRICT" if (len(invalid_vals) == 0 and null_count == 0) else (
            "CONFIRMED_NULLABLE" if len(invalid_vals) == 0 else "BROKEN"
        )
        res = {
            "child_table": child_t,
            "fk_column": fk_col,
            "parent_table": parent_t,
            "pk_column": pk_col,
            "total_records": total_child,
            "valid_references": valid_count,
            "null_references": null_count,
            "invalid_count": len(invalid_vals),
            "invalid_samples": list(invalid_vals)[:5],
            "status": status,
        }
        fk_results.append(res)
        print(f"FK: {child_t}.{fk_col} -> {parent_t}.{pk_col} | Status: {status} | Valid: {valid_count} | Null: {null_count} | Invalid: {len(invalid_vals)}")

    # Deep data quality investigations
    print("\n--- DEEP DATA QUALITY INVESTIGATION ---")

    # 1. Missing owners in Analytics_Assets
    unowned_assets = [r for r in records["Analytics_Assets"] if not r.get("owner_id")]
    print(f"1. Unowned Analytics Assets: {len(unowned_assets)} / {len(records['Analytics_Assets'])}")
    for a in unowned_assets[:5]:
        print(f"   Asset {a['asset_id']} ({a['asset_name']}) in WS {a['workspace_id']} [Audience: {a.get('estimated_audience')}]")

    # 2. Inactive owners holding assets
    inactive_owners = set(r["owner_id"] for r in records["Owners"] if r.get("status") == "inactive")
    assets_with_inactive_owners = [r for r in records["Analytics_Assets"] if r.get("owner_id") in inactive_owners]
    print(f"2. Assets assigned to INACTIVE owners: {len(assets_with_inactive_owners)}")

    # 3. KPI inconsistencies
    non_canonical_kpis = [r for r in records["KPI_Catalog"] if not r.get("canonical_metric")]
    unapproved_kpis = [r for r in records["KPI_Catalog"] if r.get("approval_status") != "approved"]
    print(f"3. KPI Catalog: {len(non_canonical_kpis)} non-canonical metrics, {len(unapproved_kpis)} unapproved metrics")

    # 4. Duplicate asset candidates (same name across different workspaces, or same model & scope)
    asset_names = Counter(r["asset_name"] for r in records["Analytics_Assets"])
    name_duplicates = {name: count for name, count in asset_names.items() if count > 1}
    print(f"4. Asset name duplicates: {len(name_duplicates)} distinct names reused across assets ({sum(name_duplicates.values())} total assets)")
    for name, c in list(name_duplicates.items())[:5]:
        sample_as = [r["asset_id"] for r in records["Analytics_Assets"] if r["asset_name"] == name]
        print(f"   Name '{name}' used in {c} assets: {sample_as}")

    # 5. Usage patterns (Zero views or very low views)
    usage_by_asset = defaultdict(lambda: {"views": 0, "unique_users": 0, "query_errors": 0, "months": 0})
    for u in records["Asset_Usage"]:
        aid = u["asset_id"]
        usage_by_asset[aid]["views"] += int(u.get("views") or 0)
        usage_by_asset[aid]["unique_users"] = max(usage_by_asset[aid]["unique_users"], int(u.get("unique_users") or 0))
        usage_by_asset[aid]["query_errors"] += int(u.get("query_errors") or 0)
        usage_by_asset[aid]["months"] += 1

    zero_view_assets = [aid for aid, stat in usage_by_asset.items() if stat["views"] == 0]
    low_view_assets = [aid for aid, stat in usage_by_asset.items() if 0 < stat["views"] < 20]
    high_error_assets = [aid for aid, stat in usage_by_asset.items() if stat["query_errors"] > 10]
    print(f"5. Usage Telemetry (over 10 months):")
    print(f"   - Assets with 0 views: {len(zero_view_assets)}")
    print(f"   - Assets with low views (<20): {len(low_view_assets)}")
    print(f"   - Assets with high query errors (>10): {len(high_error_assets)}")

    # 6. Lineage gaps
    all_asset_ids = set(r["asset_id"] for r in records["Analytics_Assets"])
    all_model_ids = set(r["model_id"] for r in records["Semantic_Models"])
    lineage_sources = set(r["source_id"] for r in records["Lineage_Edges"])
    lineage_targets = set(r["target_id"] for r in records["Lineage_Edges"])
    assets_in_lineage = (lineage_sources | lineage_targets) & all_asset_ids
    assets_missing_lineage = all_asset_ids - assets_in_lineage
    models_in_lineage = (lineage_sources | lineage_targets) & all_model_ids
    models_missing_lineage = all_model_ids - models_in_lineage
    print(f"6. Lineage Coverage:")
    print(f"   - Analytics Assets with explicit lineage edges: {len(assets_in_lineage)} / {len(all_asset_ids)}")
    print(f"   - Analytics Assets missing from lineage graph: {len(assets_missing_lineage)}")
    print(f"   - Semantic Models in lineage graph: {len(models_in_lineage)} / {len(all_model_ids)}")
    print(f"   - Semantic Models missing from lineage graph: {len(models_missing_lineage)}")

    # 7. Semantic Model AI readiness
    ai_readiness_counts = Counter(r.get("ai_readiness") for r in records["Semantic_Models"])
    ai_issue_counts = Counter(r.get("ai_issue_pattern") for r in records["Semantic_Models"])
    refresh_counts = Counter(r.get("refresh_status") for r in records["Semantic_Models"])
    print(f"7. Semantic Models Readiness:")
    print(f"   - AI Readiness: {dict(ai_readiness_counts)}")
    print(f"   - AI Issues: {dict(ai_issue_counts)}")
    print(f"   - Refresh Status: {dict(refresh_counts)}")

    # 8. Migration Backlog analysis
    rec_paths = Counter(r.get("recommended_path_candidate") for r in records["Migration_Backlog"])
    complexities = Counter(r.get("complexity") for r in records["Migration_Backlog"])
    statuses = Counter(r.get("status") for r in records["Migration_Backlog"])
    print(f"8. Migration Backlog (94 Tableau assets):")
    print(f"   - Recommended Paths: {dict(rec_paths)}")
    print(f"   - Complexity: {dict(complexities)}")
    print(f"   - Status: {dict(statuses)}")

    # Save comprehensive results to JSON (strip raw_records to keep JSON manageable)
    clean_profiles = {}
    for s_name, prof in sheets_profile.items():
        clean_prof = {k: v for k, v in prof.items() if k != "raw_records"}
        clean_profiles[s_name] = clean_prof

    output_data = {
        "profiling_date": datetime.now().isoformat(),
        "workbook_path": WORKBOOK_PATH,
        "sheets": clean_profiles,
        "foreign_keys": fk_results,
        "dq_investigations": {
            "unowned_assets": [a["asset_id"] for a in unowned_assets],
            "assets_with_inactive_owners": [a["asset_id"] for a in assets_with_inactive_owners],
            "non_canonical_kpis": [k["kpi_id"] for k in non_canonical_kpis],
            "unapproved_kpis": [k["kpi_id"] for k in unapproved_kpis],
            "name_duplicates": name_duplicates,
            "zero_view_assets": zero_view_assets,
            "low_view_assets": low_view_assets,
            "high_error_assets": high_error_assets,
            "assets_missing_lineage": list(assets_missing_lineage),
            "models_missing_lineage": list(models_missing_lineage),
            "ai_readiness": dict(ai_readiness_counts),
            "ai_issues": dict(ai_issue_counts),
            "refresh_status": dict(refresh_counts),
            "migration_paths": dict(rec_paths),
            "migration_complexity": dict(complexities),
        }
    }

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"\nSaved profiling output to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()

