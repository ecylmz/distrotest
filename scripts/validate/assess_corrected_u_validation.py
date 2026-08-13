#!/usr/bin/env python3
"""Join frozen validation evidence to the globally corrected production U states."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V = ROOT / "data/validation"
OUT = ROOT / "data/derived"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    protocol = json.loads((V / "u_positive_validation_protocol.json").read_text())
    positive = json.loads((V / "u_positive_certificates.json").read_text())
    searched = json.loads((V / "u_nonpositive_counterexample_search.json").read_text())
    production = json.loads((OUT / "automatic_upl_labels_primary.json").read_text())
    transitions = json.loads((OUT / "u_label_transitions_v1.1.0_to_v1.2.0.json").read_text())

    protocol_case = {
        (row["canonical_upstream"], row["distribution"]): row["case_id"]
        for row in protocol["positive_cases"] + protocol["counterexample_cases"]
    }
    old_positive = {row["case_id"]: row for row in positive["certificates"]}
    searched_by_id = {row["case_id"]: row for row in searched["records"]}
    changed = {(row["canonical_upstream"], row["distribution"]): row for row in transitions["records"] if row["changed"]}
    final_positive = [row for row in production["u"] if row["state"] == "U_TEST_ENTRYPOINT_RESOLVED"]
    records = []
    for row in final_positive:
        key = (row["canonical_upstream"], row["distribution"])
        case_id = protocol_case[key]
        if case_id in old_positive:
            source = old_positive[case_id]
            confirmed = source["certificate_status"] == "ORTHOGONAL_POSITIVE_CERTIFIED"
            path_count = source["positive_path_count"]
            evidence_origin = "EXHAUSTIVE_ORIGINAL_POSITIVE_CERTIFICATION"
        else:
            source = searched_by_id[case_id]
            confirmed = source["counterexample_status"] == "INDEPENDENT_COUNTEREXAMPLE_CONFIRMED"
            path_count = source["positive_path_count"]
            evidence_origin = "FROZEN_COUNTEREXAMPLE_SEARCH_THEN_GLOBAL_CORRECTION"
            if key not in changed:
                raise RuntimeError(f"NEW_POSITIVE_WITHOUT_TRANSITION:{key}")
        records.append({
            "case_id": case_id,
            "canonical_upstream": key[0],
            "distribution": key[1],
            "production_family_v1_2": row.get("family"),
            "validation_status": "POSITIVE_CLAIM_CONFIRMED" if confirmed else "VALIDATION_INDETERMINATE",
            "positive_path_count": path_count,
            "evidence_origin": evidence_origin,
            "resolved_entrypoint": source.get("resolved_entrypoint"),
            "source_sha256": source.get("source_sha256"),
        })
    confirmed_counterexamples = {
        (row["canonical_upstream"], row["distribution"])
        for row in searched["records"]
        if row["counterexample_status"] == "INDEPENDENT_COUNTEREXAMPLE_CONFIRMED"
    }
    if set(changed) != confirmed_counterexamples:
        raise RuntimeError("GLOBAL_CORRECTION_DOES_NOT_EQUAL_FROZEN_CONFIRMED_COUNTEREXAMPLES")

    family: dict[str, Counter] = defaultdict(Counter)
    for row in records:
        family[row["production_family_v1_2"] or "unknown"][row["validation_status"]] += 1
    counts = Counter(row["validation_status"] for row in records)
    payload = {
        "schema_version": "1.0",
        "disposition": "U_VALIDATION_DISCLOSED_LIMITATION",
        "claim_scope": "Corrected production-positive supported-entrypoint decisions and generic supported-domain missed-entrypoint mechanisms; not full corpus-wide U accuracy.",
        "final_positive_count": len(records),
        "confirmed_count": counts["POSITIVE_CLAIM_CONFIRMED"],
        "indeterminate_count": counts["VALIDATION_INDETERMINATE"],
        "contradicted_count": 0,
        "one_path_confirmed": sum(row["validation_status"] == "POSITIVE_CLAIM_CONFIRMED" and row["positive_path_count"] == 1 for row in records),
        "two_path_confirmed": sum(row["validation_status"] == "POSITIVE_CLAIM_CONFIRMED" and row["positive_path_count"] == 2 for row in records),
        "family_certification": {name: dict(sorted(values.items())) for name, values in sorted(family.items())},
        "counterexample_search": {
            "searched_count": searched["case_count"],
            "confirmed_before_correction": searched["confirmed_count"],
            "unresolved_candidate_count": searched["unresolved_candidate_count"],
            "globally_corrected_count": len(changed),
            "uncorrected_confirmed_count": 0,
        },
        "generic_defect": "Production U v1.1 inspected only root-level CMake/Meson surfaces and recognized only a narrow bare check Make target; v1.2 globally adds concrete nested CMake/Meson test declarations and test/check-* Make targets.",
        "rq1_changed": True,
        "records": records,
        "provenance": {
            "protocol_sha256": sha(V / "u_positive_validation_protocol.json"),
            "frozen_positive_certificates_sha256": sha(V / "u_positive_certificates.json"),
            "frozen_counterexample_search_sha256": sha(V / "u_nonpositive_counterexample_search.json"),
            "frozen_validation_outputs_sha256": sha(V / "u_positive_output_freeze.json"),
            "corrected_production_labels_sha256": sha(OUT / "automatic_upl_labels_primary.json"),
            "transition_table_sha256": sha(OUT / "u_label_transitions_v1.1.0_to_v1.2.0.json"),
        },
    }
    if (payload["final_positive_count"], payload["confirmed_count"], payload["indeterminate_count"], payload["one_path_confirmed"], payload["two_path_confirmed"]) != (115, 93, 22, 72, 21):
        raise RuntimeError("UNEXPECTED_CORRECTED_VALIDATION_COUNTS")
    (V / "u_corrected_production_assessment.json").write_bytes(canonical(payload))
    print(json.dumps({key: payload[key] for key in ("disposition", "final_positive_count", "confirmed_count", "indeterminate_count", "one_path_confirmed", "two_path_confirmed")}, indent=2))


if __name__ == "__main__":
    main()
