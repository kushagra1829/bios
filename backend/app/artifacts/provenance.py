import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


def compute_sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_artifact_provenance(
    spec_dict: Dict[str, Any],
    generated_files: Dict[str, str],
    generator_version: str = "1.0.0",
    dataset_version: str = "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx",
) -> Dict[str, Any]:
    spec_canonical = json.dumps(spec_dict, sort_keys=True)
    spec_hash = compute_sha256_text(spec_canonical)

    file_manifest = {}
    for rel_path, abs_path in generated_files.items():
        if os.path.exists(abs_path):
            file_manifest[rel_path] = {
                "size_bytes": os.path.getsize(abs_path),
                "sha256": compute_sha256_file(abs_path),
            }

    return {
        "generator_version": generator_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "spec_hash": spec_hash,
        "dataset_source": dataset_version,
        "file_count": len(file_manifest),
        "file_manifest": file_manifest,
        "generator_engine": "BIOS_PowerBI_Artifact_Factory",
        "powerbi_format": "PBIP (TMDL + PBIR)",
    }

