#!/usr/bin/env python3
"""Build the release file inventory and research-workspace provenance record."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/release_manifest.json"
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "work",
    "reproduced",
    "recollected",
    "native_outputs",
    "u_positive_native_outputs",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT or EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts):
            continue
        files.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    payload = {
        "schema_version": "1.0",
        "source_repository": {
            "packaging_source_commit": "d5b9ad3dd5b7988cb53a716f1b9d343af9a7acdb",
            "authoritative_analysis_commit": "996f3b05d19da17fa80fdfd30700b3306c44f888",
            "frozen_sample_commit": "7973b0feeb5b16d1c162b62b25a1012d610f0488",
            "final_classifier_commit": "f2492eb246054f8ee1760b3d464a1fe65ba3c0cc",
            "u_validation_output_commit": "85db86d25fe3de1c43563fea83d3397a3e8321df",
            "frame_validation_commit": "149e4072ab9cb87d8058f086af69593d52e6a732",
            "l_validation_comparison_commit": "b7b9229e8dfd6250642a037fad4cebec160edf97",
        },
        "redistribution": {
            "included": "normalized source-index metadata, frozen manifests, derived labels, result files, validation certificates, data dictionary, observed schemas, and explanatory case codebook",
            "not_included": "raw upstream source archives, extracted source trees, raw build records, and normalized build logs",
        },
        "files": files,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes((json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    print(json.dumps({"files": len(files), "bytes": sum(row["bytes"] for row in files), "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
