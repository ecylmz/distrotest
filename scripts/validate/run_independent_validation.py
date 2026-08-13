#!/usr/bin/env python3
"""Run label-blind U, frame, and L validation paths deterministically."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from distrotest_lite_validation.frame_identity import independent_identity
from distrotest_lite_validation.log_success import ADVERSARIAL_NEGATIVES, validate_line, validate_log
from distrotest_lite_validation.native_u import validate_case as validate_native
from distrotest_lite_validation.structured_u import validate_case as validate_structured


ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "data/validation"
PHASE0 = ROOT / "data/manifests/source_indices"
FROOT = ROOT / "data/work"
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


def run_u() -> None:
    blind = json.loads((VALIDATION / "u88_blind_input.json").read_text())
    forbidden = {"state", "production_u", "production_p", "production_l", "labels", "rq1"}
    for frozen_record in blind["records"]:
        record = release_record(frozen_record)
        if forbidden & set(record):
            raise RuntimeError(f"BLIND_INPUT_CONTAINS_FORBIDDEN_LABEL:{record['case_id']}")
    a, b = [], []
    native_dir = VALIDATION / "native_outputs/a"
    native_dir.mkdir(parents=True, exist_ok=True)
    for stale in native_dir.glob("*.txt"):
        stale.unlink()
    for frozen_record in blind["records"]:
        record = release_record(frozen_record)
        cert_a, outputs = validate_native(record, ROOT)
        cert_b = validate_structured(record, ROOT)
        a.append(cert_a); b.append(cert_b)
        for name, payload in outputs.items():
            (native_dir / name).write_bytes(payload)
    write("u88_validator_a.json", {"schema_version": "1.0", "validator": "A_NATIVE", "case_count": len(a), "certificates": a})
    write("u88_validator_b.json", {"schema_version": "1.0", "validator": "B_STRUCTURED", "case_count": len(b), "certificates": b})
    consensus = []
    for ca, cb in zip(a, b, strict=True):
        sa, sb = ca["reference_state"], cb["reference_state"]
        if sa == sb and sa != "VALIDATION_INDETERMINATE":
            status, state = "AUTOMATED_REFERENCE_AGREEMENT", sa
        elif sa == sb:
            status, state = "VALIDATION_INDETERMINATE", None
        elif "VALIDATION_INDETERMINATE" in {sa, sb}:
            status, state = "SINGLE_PATH_CONFIRMATION", sb if sa == "VALIDATION_INDETERMINATE" else sa
        else:
            status, state = "AUTOMATED_VALIDATION_DISAGREEMENT", None
        consensus.append({"case_id": ca["case_id"], "validator_a_state": sa, "validator_b_state": sb, "consensus_status": status, "automated_reference_state": state})
    write("u88_validation_consensus.json", {"schema_version": "1.0", "case_count": len(consensus), "status_counts": dict(sorted(Counter(row["consensus_status"] for row in consensus).items())), "records": consensus})


def run_frame() -> None:
    rows_by_distro = {d: json.loads((PHASE0 / f"{d}_sources.json").read_text())["records"] for d in ("debian", "fedora")}
    records = []
    grouped: dict[str, dict[str, list[str]]] = {"debian": defaultdict(list), "fedora": defaultdict(list)}
    for distro in ("debian", "fedora"):
        for row in rows_by_distro[distro]:
            raw = row.get("homepage", "")
            result = independent_identity(raw)
            records.append({"distribution": distro, "source": row["source"], "raw_url_sha256": hashlib.sha256(raw.encode()).hexdigest(), **result})
            if result["identity"]:
                grouped[distro][result["identity"]].append(row["source"])
    collisions = []
    for distro, groups in grouped.items():
        for identity, sources in sorted(groups.items()):
            if len(sources) > 1:
                collisions.append({"distribution": distro, "identity": identity, "source_count": len(sources), "sources": sorted(sources), "ambiguous": True})
    shared = sorted(set(grouped["debian"]) & set(grouped["fedora"]))
    retained = [identity for identity in shared if len(grouped["debian"][identity]) == len(grouped["fedora"][identity]) == 1]
    write("frame_independent_validation.json", {"schema_version": "1.0", "implementation": "host_grammar_v1.0", "input_counts": {d: len(v) for d, v in rows_by_distro.items()}, "resolved_url_count": sum(row["status"] == "RESOLVED" for row in records), "unresolved_url_count": sum(row["status"] != "RESOLVED" for row in records), "shared_identity_count": len(shared), "retained_matched_project_count": len(retained), "excluded_ambiguous_identity_count": len(shared) - len(retained), "records": records})
    write("frame_collision_report.json", {"schema_version": "1.0", "collision_count": len(collisions), "collisions": collisions, "shared_identities": shared, "retained_matched_projects": retained})


def run_l() -> None:
    log_root = FROOT / "normalized/logs"
    certificates = [validate_log(path, FROOT) for path in sorted(log_root.glob("**/*.log"))]
    candidates = [{"log": row["log"], "log_sha256": row["log_sha256"], "candidates": row["candidates"]} for row in certificates if row["candidates"]]
    adversarial = [{"text_sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text, "result": validate_line(text)} for text in ADVERSARIAL_NEGATIVES]
    write("l_sensitivity_independent_validation.json", {"schema_version": "1.0", "corpus_count": len(certificates), "positive_log_count": sum(row["reference_positive"] for row in certificates), "certificates": certificates})
    write("l_sensitivity_candidates.json", {"schema_version": "1.0", "candidate_log_count": len(candidates), "records": candidates})
    write("l_sensitivity_adversarial_results.json", {"schema_version": "1.0", "fixture_count": len(adversarial), "rejected_count": sum(not row["result"] or not row["result"]["positive"] for row in adversarial), "records": adversarial})


if __name__ == "__main__":
    VALIDATION.mkdir(parents=True, exist_ok=True)
    run_u(); run_frame(); run_l()
