import os
import uuid
from typing import Dict, List
from backend.app.artifacts.schemas import DashboardSpec, MeasureSpec, RelationshipSpec
from backend.app.artifacts.template_manager import BAYER_TABLE_SCHEMAS


def _make_guid() -> str:
    return str(uuid.uuid4())


def generate_database_tmdl(database_name: str) -> str:
    return f"""database '{database_name}'
\tcompatibilityLevel: 1567
"""


def generate_model_tmdl() -> str:
    return """model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 0
annotation PBIDesktopVersion = 2.138.1452.0 (24.11)
"""


def generate_table_tmdl(table_name: str, measures_for_table: List[MeasureSpec]) -> str:
    schema = BAYER_TABLE_SCHEMAS.get(table_name, {})
    lines = [f"table '{table_name}'", f"\tlineageTag: {_make_guid()}", ""]

    # Generate columns
    for col_name, data_type in schema.items():
        summarize_by = "sum" if data_type in ("double", "int64") and not col_name.endswith("_id") and not col_name == "month" else "none"
        if "pct" in col_name or "variance" in col_name:
            summarize_by = "average"
        lines.append(f"\tcolumn '{col_name}'")
        lines.append(f"\t\tdataType: {data_type}")
        lines.append(f"\t\tsourceColumn: {col_name}")
        lines.append(f"\t\tsummarizeBy: {summarize_by}")
        lines.append(f"\t\tlineageTag: {_make_guid()}")
        lines.append("")

    # Generate measures
    for m in measures_for_table:
        lines.append(f"\tmeasure '{m.name}' = {m.dax_expression}")
        lines.append(f"\t\tformatString: \"{m.format_string}\"")
        lines.append(f"\t\tlineageTag: {_make_guid()}")
        if m.description:
            lines.append(f"\t\tdescription: \"{m.description}\"")
        lines.append("")

    # Source partition
    lines.append(f"\tpartition '{table_name}' = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\tlet")
    lines.append(f"\t\t\t    Source = Sql.Database(\"localhost\", \"bios\", [Query=\"SELECT * FROM {table_name}\"])")
    lines.append("\t\t\tin")
    lines.append("\t\t\t    Source")
    lines.append("")

    return "\n".join(lines)


def generate_relationships_tmdl(relationships: List[RelationshipSpec]) -> str:
    lines = []
    for rel in relationships:
        lines.append(f"relationship {rel.name}")
        lines.append(f"\tfromColumn: '{rel.from_table}'.'{rel.from_column}'")
        lines.append(f"\ttoColumn: '{rel.to_table}'.'{rel.to_column}'")
        if not rel.is_active:
            lines.append("\tisActive: false")
        if rel.cross_filtering_behavior != "oneDirection":
            lines.append(f"\tcrossFilteringBehavior: {rel.cross_filtering_behavior}")
        lines.append("")
    return "\n".join(lines)


def generate_semantic_model_files(spec: DashboardSpec, semantic_model_dir: str) -> Dict[str, str]:
    definition_dir = os.path.join(semantic_model_dir, "definition")
    tables_dir = os.path.join(definition_dir, "tables")
    os.makedirs(tables_dir, exist_ok=True)

    generated = {}

    # 1. definition.pbidataset
    pbidataset_path = os.path.join(semantic_model_dir, "definition.pbidataset")
    with open(pbidataset_path, "w", encoding="utf-8") as f:
        f.write('{\n  "version": "1.0",\n  "settings": {}\n}\n')
    generated["definition.pbidataset"] = pbidataset_path

    # 2. database.tmdl
    db_tmdl_path = os.path.join(definition_dir, "database.tmdl")
    with open(db_tmdl_path, "w", encoding="utf-8") as f:
        f.write(generate_database_tmdl(spec.title))
    generated["definition/database.tmdl"] = db_tmdl_path

    # 3. model.tmdl
    model_tmdl_path = os.path.join(definition_dir, "model.tmdl")
    with open(model_tmdl_path, "w", encoding="utf-8") as f:
        f.write(generate_model_tmdl())
    generated["definition/model.tmdl"] = model_tmdl_path

    # Group measures by table
    measures_by_table: Dict[str, List[MeasureSpec]] = {t: [] for t in spec.tables}
    for m in spec.measures:
        if m.table_name in measures_by_table:
            measures_by_table[m.table_name].append(m)
        else:
            measures_by_table[spec.tables[0]].append(m)

    # 4. table TMDLs
    for t in spec.tables:
        table_path = os.path.join(tables_dir, f"{t}.tmdl")
        with open(table_path, "w", encoding="utf-8") as f:
            f.write(generate_table_tmdl(t, measures_by_table.get(t, [])))
        generated[f"definition/tables/{t}.tmdl"] = table_path

    # 5. relationships.tmdl
    if spec.relationships:
        rel_path = os.path.join(definition_dir, "relationships.tmdl")
        with open(rel_path, "w", encoding="utf-8") as f:
            f.write(generate_relationships_tmdl(spec.relationships))
        generated["definition/relationships.tmdl"] = rel_path

    return generated

