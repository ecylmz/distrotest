#!/usr/bin/env python3
"""Execute the frozen 99-positive certification and 301-case counterexample search."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from distrotest_lite_validation.u_positive import counterexample_search, positive_certificate, sha256


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "data/validation"
PROTOCOL = VALIDATION / "u_positive_validation_protocol.json"
NATIVE = VALIDATION / "u_positive_native_outputs"
LEGACY_SOURCE_PREFIX = "full_study/distrotest-lite:v1.1:full-study:sample/"


def release_record(record: dict) -> dict:
    result = dict(record)
    source_tree = result.get("source_tree")
    if source_tree and source_tree.startswith(LEGACY_SOURCE_PREFIX):
        result["source_tree"] = "data/work/" + source_tree.removeprefix(LEGACY_SOURCE_PREFIX)
    return result


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write(name: str, value: object) -> None:
    (VALIDATION / name).write_bytes(canonical(value))


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    NATIVE.mkdir(parents=True, exist_ok=True)
    for stale in NATIVE.glob("*.txt"):
        stale.unlink()
    output_prefix = NATIVE.relative_to(ROOT).as_posix()
    positives = []
    counterexamples = []
    for frozen_record in protocol["positive_cases"]:
        record = release_record(frozen_record)
        certificate, outputs = positive_certificate(record, ROOT, output_prefix)
        positives.append(certificate)
        for name, payload in outputs.items():
            (NATIVE / name).write_bytes(payload)
    for frozen_record in protocol["counterexample_cases"]:
        record = release_record(frozen_record)
        result, outputs = counterexample_search(record, ROOT, output_prefix)
        counterexamples.append(result)
        for name, payload in outputs.items():
            (NATIVE / name).write_bytes(payload)

    family_counts: dict[str, Counter] = defaultdict(Counter)
    for row in positives:
        family = "+".join(row["family"]) or "no_applicable_independent_backend"
        family_counts[family][row["certificate_status"]] += 1
    positive_payload = {
        "schema_version": "1.0",
        "protocol_sha256": sha256(PROTOCOL),
        "case_count": len(positives),
        "certificate_status_counts": dict(sorted(Counter(row["certificate_status"] for row in positives).items())),
        "path_coverage": {
            "one_path_certified": sum(row["positive_path_count"] == 1 for row in positives),
            "two_path_certified": sum(row["positive_path_count"] == 2 for row in positives),
            "indeterminate": sum(row["certificate_status"] == "CERTIFICATION_INDETERMINATE" for row in positives),
            "contradicted": sum(row["certificate_status"] == "ORTHOGONAL_POSITIVE_CONTRADICTED" for row in positives),
        },
        "family_certification": {key: dict(sorted(value.items())) for key, value in sorted(family_counts.items())},
        "certificates": positives,
    }
    candidates = [row for row in counterexamples if row["counterexample_status"] != "NO_CLEAR_COUNTEREXAMPLE_FOUND"]
    counter_payload = {
        "schema_version": "1.0",
        "protocol_sha256": sha256(PROTOCOL),
        "case_count": len(counterexamples),
        "status_counts": dict(sorted(Counter(row["counterexample_status"] for row in counterexamples).items())),
        "confirmed_count": sum(row["counterexample_status"] == "INDEPENDENT_COUNTEREXAMPLE_CONFIRMED" for row in counterexamples),
        "unresolved_candidate_count": sum(row["counterexample_status"] == "COUNTEREXAMPLE_CANDIDATE_UNRESOLVED" for row in counterexamples),
        "candidate_case_ids": [row["case_id"] for row in candidates],
        "records": counterexamples,
    }
    write("u_positive_certificates.json", positive_payload)
    write("u_nonpositive_counterexample_search.json", counter_payload)
    summary = {
        "schema_version": "1.0",
        "protocol_sha256": sha256(PROTOCOL),
        "positive": positive_payload["path_coverage"],
        "positive_status_counts": positive_payload["certificate_status_counts"],
        "counterexample_status_counts": counter_payload["status_counts"],
        "generic_defect_assessment": "PENDING_FROZEN_OUTPUT_REVIEW" if candidates else "NO_DEMONSTRATED_GENERIC_DEFECT",
    }
    write("u_positive_validation_summary.json", summary)


if __name__ == "__main__":
    main()
