import json
import os
import uuid
from typing import Any, Dict, List
from backend.app.artifacts.schemas import DashboardSpec, PageSpec, VisualSpec
from backend.app.artifacts.template_manager import BIOS_PALETTE


def _visual_type_to_pbir(visual_type: str) -> str:
    mapping = {
        "card": "card",
        "bar_chart": "clusteredBarChart",
        "line_chart": "lineChart",
        "slicer": "slicer",
        "table": "tableEx",
    }
    return mapping.get(visual_type, "card")


def _build_visual_container(visual: VisualSpec, z_order: int) -> Dict[str, Any]:
    pbir_type = _visual_type_to_pbir(visual.visual_type)
    
    projections: Dict[str, List[Any]] = {}
    if visual.visual_type == "card":
        projections["Values"] = [{"queryRef": f"{visual.table_name}.{m}"} for m in visual.measures]
    elif visual.visual_type in ("bar_chart", "line_chart"):
        projections["Category"] = [{"queryRef": f"{visual.table_name}.{f}"} for f in visual.fields]
        projections["Y"] = [{"queryRef": f"{visual.table_name}.{m}"} for m in visual.measures]
    elif visual.visual_type == "slicer":
        projections["Values"] = [{"queryRef": f"{visual.table_name}.{f}"} for f in visual.fields]
    else:
        projections["Values"] = [{"queryRef": f"{visual.table_name}.{f}"} for f in (visual.fields + visual.measures)]

    container = {
        "id": z_order + 1,
        "x": visual.position.get("x", 20),
        "y": visual.position.get("y", 20),
        "width": visual.position.get("width", 300),
        "height": visual.position.get("height", 200),
        "z": z_order,
        "config": {
            "name": visual.visual_id,
            "singleVisual": {
                "visualType": pbir_type,
                "projections": projections,
                "objects": {
                    "title": [
                        {
                            "properties": {
                                "show": {"expr": {"Literal": {"Value": "true"}}},
                                "text": {"expr": {"Literal": {"Value": f"'{visual.title}'"}}},
                            }
                        }
                    ]
                },
            },
        },
    }
    return container


def _build_page(page: PageSpec, page_index: int) -> Dict[str, Any]:
    visual_containers = []
    for idx, v in enumerate(page.visuals):
        visual_containers.append(_build_visual_container(v, idx))

    return {
        "name": page.page_name,
        "displayName": page.display_name,
        "ordinal": page_index,
        "width": 1280,
        "height": 720,
        "visualContainers": visual_containers,
    }


def generate_report_json(spec: DashboardSpec) -> str:
    sections = []
    for idx, page in enumerate(spec.pages):
        sections.append(_build_page(page, idx))

    report_structure = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/reportVersion/1.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "BIOS Custom Theme",
                "version": "1.0",
                "type": "custom",
            },
            "customTheme": {
                "name": "BIOS Theme",
                "dataColors": BIOS_PALETTE["dataColors"],
                "background": spec.theme_palette.get("background", "#F2F5F9"),
                "foreground": spec.theme_palette.get("primary", "#142438"),
                "tableAccent": spec.theme_palette.get("accent", "#3478F6"),
            },
        },
        "config": {
            "version": "5.50",
            "theme": "BIOS Theme",
            "defaultDrillFilterOtherVisuals": True,
        },
        "sections": sections,
    }
    return json.dumps(report_structure, indent=2)


def generate_report_files(spec: DashboardSpec, report_dir: str, semantic_model_name: str) -> Dict[str, str]:
    definition_dir = os.path.join(report_dir, "definition")
    os.makedirs(definition_dir, exist_ok=True)

    generated = {}

    # 1. definition.pbir
    pbir_path = os.path.join(report_dir, "definition.pbir")
    pbir_content = {
        "version": "4.0",
        "datasetReference": {
            "byPath": {
                "path": f"../{semantic_model_name}"
            },
            "byConnection": None
        }
    }
    with open(pbir_path, "w", encoding="utf-8") as f:
        json.dump(pbir_content, f, indent=2)
    generated["definition.pbir"] = pbir_path

    # 2. definition/report.json
    report_json_path = os.path.join(definition_dir, "report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        f.write(generate_report_json(spec))
    generated["definition/report.json"] = report_json_path

    return generated

