#!/usr/bin/env python3
"""Reconstruct the corrected Debian--Fedora matched frame from frozen indices."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from distrotest_lite.common import canonical_json
from distrotest_lite.repositories import canonical_url, upstream_version


ROOT = Path(__file__).resolve().parents[2]
INDICES = ROOT / "data/manifests/source_indices"


def main() -> None:
    records = {
        distro: json.loads((INDICES / f"{distro}_sources.json").read_text())["records"]
        for distro in ("debian", "fedora")
    }
    grouped: dict[str, dict[str, list[dict]]] = {}
    for distro, rows in records.items():
        by_identity: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            identity, _ = canonical_url(row.get("homepage", ""))
            if identity:
                by_identity[identity].append(row)
        grouped[distro] = by_identity

    resolved = []
    for identity in sorted(set(grouped["debian"]) & set(grouped["fedora"])):
        debian = grouped["debian"][identity]
        fedora = grouped["fedora"][identity]
        if len(debian) != 1 or len(fedora) != 1:
            continue
        debian_versions = sorted({upstream_version("debian", row) for row in debian})
        fedora_versions = sorted({upstream_version("fedora", row) for row in fedora})
        resolved.append(
            {
                "canonical_upstream": identity,
                "stratum": "C2V"
                if debian_versions == fedora_versions and len(debian_versions) == 1 and debian_versions[0] is not None
                else "NON_C2V",
            }
        )

    expected = {"C2V": 3694, "NON_C2V": 3256}
    counts = {stratum: sum(row["stratum"] == stratum for row in resolved) for stratum in expected}
    if counts != expected:
        raise RuntimeError(f"FRAME_COUNT_MISMATCH:{counts}:{expected}")

    sample = json.loads((ROOT / "data/manifests/sample_revision.json").read_text())
    namespace = sample["namespace"]

    def selection_hash(identity: str) -> str:
        return hashlib.sha256((namespace + "\0" + identity).encode()).hexdigest()

    selected = set()
    for stratum, size in (("C2V", 170), ("NON_C2V", 30)):
        candidates = [row for row in resolved if row["stratum"] == stratum]
        chosen = sorted(candidates, key=lambda row: (selection_hash(row["canonical_upstream"]), row["canonical_upstream"]))[:size]
        selected.update(row["canonical_upstream"] for row in chosen)
    frozen = {row["canonical_upstream"] for row in sample["projects"]}
    if selected != frozen:
        raise RuntimeError("RECONSTRUCTED_SAMPLE_MEMBERSHIP_MISMATCH")

    result = {
        "method_version": "lineage-v1.2.0-host-aware-forge-paths",
        "resolved_projects": len(resolved),
        "strata": counts,
        "sample_membership_unchanged": True,
        "selected_project_count": len(selected),
        "source_indices": {
            distro: {
                "path": f"data/manifests/source_indices/{distro}_sources.json",
                "sha256": hashlib.sha256((INDICES / f"{distro}_sources.json").read_bytes()).hexdigest(),
            }
            for distro in ("debian", "fedora")
        },
    }
    output = ROOT / "results/reproduced/frame_reconstruction.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(result))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
