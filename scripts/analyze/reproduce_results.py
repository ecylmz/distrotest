#!/usr/bin/env python3
"""Recompute RQ1--RQ3 and retained sensitivities from frozen analysis inputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from distrotest_lite.classifiers import classify_l_text
from distrotest_lite.common import canonical_json
from distrotest_lite.revision_analysis import analyze_revision


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sensitivity_labels(primary: dict, logs: list[dict], work_root: Path) -> dict:
    result = copy.deepcopy(primary)
    rows = []
    for log in logs:
        if log["state"] == "AVAILABLE":
            classified = classify_l_text(
                (work_root / log["normalized_path"]).read_text(errors="replace"),
                include_posthoc_success_rule=True,
            )
        else:
            classified = {"state": log["state"], "evidence": [], "zero_evidence": []}
        rows.append(
            {
                "canonical_upstream": log["canonical_upstream"],
                "distribution": log["distribution"],
                "source_log_sha256": log.get("raw_sha256"),
                "source_log": log.get("official_identifier"),
                **classified,
            }
        )
    rows.sort(key=lambda row: (row["canonical_upstream"], row["distribution"]))
    result["l"] = rows
    result["rule_versions"] = {
        **result["rule_versions"],
        "l": "l-rules-v1.3.0-posthoc-generic-success-sensitivity",
    }
    return result


def typed_rows(primary: dict, sensitivity: dict) -> dict:
    rows = []
    for distro in ("debian", "fedora"):
        retrievability = primary["retrievability"][distro]
        rows.append(
            {
                "panel": "RQ1",
                "metric": "record_retrievability",
                "distribution": distro,
                "point": retrievability["weighted_proportion"],
                "interval": retrievability["weighted_bootstrap_ci"],
                "interval_method": "stratified_project_percentile_bootstrap",
                "count": retrievability["positive_count"],
                "denominator": retrievability["denominator"],
                "weighting": "design_weighted",
            }
        )
        for metric in ("conditional", "overall"):
            source = primary["rq1"][distro][metric]
            rows.append(
                {
                    "panel": "RQ1",
                    "metric": metric + "_positive_evidence",
                    "distribution": distro,
                    "point": source["weighted_proportion"],
                    "interval": source["weighted_bootstrap_ci"],
                    "interval_method": "stratified_project_percentile_bootstrap",
                    "count": source["positive_count"],
                    "denominator": source["denominator"],
                    "weighting": "design_weighted",
                }
            )
        for analysis, result in (("revised_primary", primary), ("posthoc_l_sensitivity", sensitivity)):
            for category in ("P_TEST_DECLARED", "P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED"):
                source = next(row for row in result["rq2"][distro]["rows"] if row["category"] == category)
                sparse = source["positive_count"] == 0
                rows.append(
                    {
                        "panel": "RQ2",
                        "analysis": analysis,
                        "metric": category,
                        "distribution": distro,
                        "point": source["weighted_proportion"],
                        "interval": source["unweighted_wilson_ci"] if sparse else source["weighted_bootstrap_ci"],
                        "interval_method": "unweighted_wilson_sparse_zero" if sparse else "stratified_project_percentile_bootstrap",
                        "count": source["positive_count"],
                        "denominator": source["denominator"],
                        "weighting": "design_weighted_point",
                    }
                )
    return {"schema_version": "1.0", "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-work", action="store_true", help="use freshly acquired and classified data/work inputs")
    args = parser.parse_args()

    sample = load(ROOT / "data/manifests/sample_revision.json")
    if args.from_work:
        work = ROOT / "data/work"
        labels = load(work / "derived/automatic_upl_labels.json")
        logs = load(work / "derived/log_acquisition.json")["records"]
        c2a = load(work / "derived/c2a.json")
        sensitivity = sensitivity_labels(labels, logs, work)
        output = ROOT / "results/recollected"
    else:
        labels = load(ROOT / "data/derived/automatic_upl_labels_primary.json")
        sensitivity = load(ROOT / "data/derived/automatic_upl_labels_posthoc_l_sensitivity.json")
        logs = load(ROOT / "data/manifests/log_acquisition.json")["records"]
        c2a = load(ROOT / "data/manifests/c2a_primary_archive.json")
        output = ROOT / "results/reproduced"

    primary_results, primary_bootstrap = analyze_revision(sample, labels, logs, c2a)
    sensitivity_results, sensitivity_bootstrap = analyze_revision(sample, sensitivity, logs, c2a)
    typed = typed_rows(primary_results, sensitivity_results)

    paths = {
        "primary": output / "scientific_results_primary.json",
        "sensitivity": output / "scientific_results_posthoc_l_sensitivity.json",
        "typed": output / "typed_results.json",
        "primary_bootstrap": output / "bootstrap_primary.json",
        "sensitivity_bootstrap": output / "bootstrap_posthoc_l_sensitivity.json",
    }
    write(paths["primary"], primary_results)
    write(paths["sensitivity"], sensitivity_results)
    write(paths["typed"], typed)
    write(paths["primary_bootstrap"], primary_bootstrap)
    write(paths["sensitivity_bootstrap"], sensitivity_bootstrap)

    checks = {}
    if not args.from_work:
        authoritative = {
            "primary": ROOT / "results/authoritative/scientific_results_primary.json",
            "sensitivity": ROOT / "results/authoritative/scientific_results_posthoc_l_sensitivity.json",
            "typed": ROOT / "results/authoritative/typed_results.json",
        }
        checks = {name: sha256(paths[name]) == sha256(reference) for name, reference in authoritative.items()}
        if not all(checks.values()):
            raise RuntimeError(f"AUTHORITATIVE_RESULT_MISMATCH:{checks}")

    summary = {
        "input": "recollected" if args.from_work else "frozen",
        "authoritative_byte_matches": checks,
        "retrievable_logs": {
            distro: primary_results["retrievability"][distro]["positive_count"]
            for distro in ("debian", "fedora")
        },
        "rq3_counts": primary_results["rq3"]["counts"],
        "output_directory": str(output.relative_to(ROOT)),
    }
    write(output / "reproduction_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
