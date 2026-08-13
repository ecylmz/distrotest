#!/usr/bin/env python3
"""Join frozen independent evidence to production U/frame/L outputs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from distrotest_lite.repositories import canonical_url


ROOT = Path(__file__).resolve().parents[2]
V = ROOT / "data/validation"
PHASE0 = ROOT / "data/manifests/source_indices"
FROOT = ROOT / "data/work"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write(name: str, value: object) -> None:
    (V / name).write_bytes(canonical(value))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze() -> dict:
    freeze_path = V / "validation_outputs_freeze.json"
    subprocess.run(["git", "ls-files", "--error-unmatch", str(freeze_path.relative_to(ROOT))], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    freeze = json.loads(freeze_path.read_text())
    for record in freeze["files"]:
        path = ROOT / record["path"].replace("revision/validation/", "data/validation/", 1)
        if sha(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise RuntimeError(f"FROZEN_OUTPUT_HASH_MISMATCH:{record['path']}")
    if freeze["deterministic_rerun"] != "BYTE_IDENTICAL":
        raise RuntimeError("DETERMINISTIC_RERUN_NOT_FROZEN")
    return freeze


def compare_u() -> None:
    blind = json.loads((V / "u88_blind_input.json").read_text())
    consensus = json.loads((V / "u88_validation_consensus.json").read_text())
    cert_a = {row["case_id"]: row for row in json.loads((V / "u88_validator_a.json").read_text())["certificates"]}
    cert_b = {row["case_id"]: row for row in json.loads((V / "u88_validator_b.json").read_text())["certificates"]}
    production = json.loads((ROOT / "data/derived/automatic_upl_labels_primary.json").read_text())
    prod = {(row["canonical_upstream"], row["distribution"]): row for row in production["u"]}
    cases = {row["case_id"]: row for row in blind["records"]}
    joined = []
    matrix: dict[str, Counter] = defaultdict(Counter)
    mechanisms = Counter()
    for record in consensus["records"]:
        source = cases[record["case_id"]]
        production_row = prod[(source["canonical_upstream"], source["distribution"])]
        reference = record["automated_reference_state"] if record["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" else None
        agreement = reference == production_row["state"] if reference else None
        mechanism = None
        if reference and not agreement:
            if reference == "U_TEST_ENTRYPOINT_RESOLVED":
                mechanism = "ORTHOGONAL_ENTRYPOINT_MISSED_BY_PRODUCTION"
            elif production_row["state"] == "U_TEST_ENTRYPOINT_RESOLVED":
                mechanism = "PRODUCTION_ENTRYPOINT_NOT_CONFIRMED_BY_TWO_PATH_REFERENCE"
            elif production_row["state"] == "U_NO_TEST_CAPABILITY_RESOLVED":
                mechanism = "PRODUCTION_ABSENCE_STATE_CONTRADICTED"
            else:
                mechanism = "NONPOSITIVE_STATE_BOUNDARY_DISAGREEMENT"
            mechanisms[mechanism] += 1
        if reference:
            matrix[production_row["state"]][reference] += 1
        joined.append({
            **record, "canonical_upstream": source["canonical_upstream"], "distribution": source["distribution"],
            "production_state": production_row["state"], "production_reason": production_row.get("reason"),
            "production_vs_reference_agreement": agreement, "error_mechanism": mechanism,
            "validator_a_certificate": cert_a[record["case_id"]], "validator_b_certificate": cert_b[record["case_id"]],
        })
    strong = [row for row in joined if row["automated_reference_state"] is not None and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT"]
    states = ["U_TEST_ENTRYPOINT_RESOLVED", "U_TEST_ASSETS_ONLY", "U_NO_TEST_CAPABILITY_RESOLVED", "U_UNRESOLVED"]
    state_specific = {}
    for state in states:
        relevant = [row for row in strong if row["production_state"] == state]
        state_specific[state] = {"production_count_in_strong_domain": len(relevant), "agreed": sum(row["production_vs_reference_agreement"] for row in relevant), "disagreed": sum(row["production_vs_reference_agreement"] is False for row in relevant)}
    positive_rows = [row for row in joined if row["production_state"] == "U_TEST_ENTRYPOINT_RESOLVED"]
    no_rows = [row for row in joined if row["production_state"] == "U_NO_TEST_CAPABILITY_RESOLVED"]
    unresolved_rows = [row for row in joined if row["production_state"] == "U_UNRESOLVED"]
    summary = {
        "case_count": len(joined), "a_b_agreement": consensus["status_counts"].get("AUTOMATED_REFERENCE_AGREEMENT", 0),
        "a_b_disagreement": consensus["status_counts"].get("AUTOMATED_VALIDATION_DISAGREEMENT", 0),
        "single_path_confirmation": consensus["status_counts"].get("SINGLE_PATH_CONFIRMATION", 0),
        "both_indeterminate": consensus["status_counts"].get("VALIDATION_INDETERMINATE", 0),
        "strong_reference_count": len(strong), "strong_reference_production_agreement": sum(row["production_vs_reference_agreement"] for row in strong),
        "strong_reference_production_disagreement": sum(row["production_vs_reference_agreement"] is False for row in strong),
        "production_entrypoint": {
            "sample_count": len(positive_rows),
            "confirmed_by_strong_reference": sum(row["automated_reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED" and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in positive_rows),
            "suspected_false_positives_two_path": sum(row["automated_reference_state"] not in {None, "U_TEST_ENTRYPOINT_RESOLVED"} and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in positive_rows),
        },
        "independently_discovered_production_false_negatives": sum(row["production_state"] != "U_TEST_ENTRYPOINT_RESOLVED" and row["automated_reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED" and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in joined),
        "production_no_capability": {"sample_count": len(no_rows), "confirmed_by_strong_reference": sum(row["automated_reference_state"] == "U_NO_TEST_CAPABILITY_RESOLVED" and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in no_rows), "entrypoint_discovered_two_path": sum(row["automated_reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED" and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in no_rows)},
        "production_unresolved": {"sample_count": len(unresolved_rows), "entrypoint_discovered_two_path": sum(row["automated_reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED" and row["consensus_status"] == "AUTOMATED_REFERENCE_AGREEMENT" for row in unresolved_rows)},
        "state_specific": state_specific, "error_mechanisms": dict(sorted(mechanisms.items())),
    }
    write("u88_production_comparison.json", {"schema_version": "1.0", "summary": summary, "confusion_matrix": {p: dict(sorted(values.items())) for p, values in sorted(matrix.items())}, "records": joined})


def compare_frame() -> None:
    independent = json.loads((V / "frame_independent_validation.json").read_text())
    independent_rows = {(row["distribution"], row["source"]): row for row in independent["records"]}
    disagreements = []
    agreement = both = 0
    production_groups = {"debian": defaultdict(list), "fedora": defaultdict(list)}
    for distro in ("debian", "fedora"):
        rows = json.loads((PHASE0 / f"{distro}_sources.json").read_text())["records"]
        for row in rows:
            prod_identity, method = canonical_url(row.get("homepage", ""))
            ref = independent_rows[(distro, row["source"])]
            if prod_identity and ref["identity"]:
                both += 1
                if prod_identity == ref["identity"]:
                    agreement += 1
                else:
                    disagreements.append({"distribution": distro, "source": row["source"], "raw_url_sha256": ref["raw_url_sha256"], "production_identity": prod_identity, "independent_identity": ref["identity"], "host": ref.get("host"), "mechanism": "HOST_PATH_GRAMMAR_DISAGREEMENT"})
            if prod_identity:
                production_groups[distro][prod_identity].append(row["source"])
    shared = set(production_groups["debian"]) & set(production_groups["fedora"])
    retained = sorted(identity for identity in shared if len(production_groups["debian"][identity]) == len(production_groups["fedora"][identity]) == 1)
    independent_retained = set(json.loads((V / "frame_collision_report.json").read_text())["retained_matched_projects"])
    write("frame_production_vs_independent.json", {
        "schema_version": "1.0", "both_resolved_url_count": both, "identity_agreement_count": agreement,
        "identity_disagreement_count": len(disagreements), "independent_implementation_agreement": agreement / both if both else None,
        "production_retained_matched_project_count": len(retained), "independent_retained_matched_project_count": len(independent_retained),
        "retained_only_production": sorted(set(retained) - independent_retained), "retained_only_independent": sorted(independent_retained - set(retained)),
        "disagreement_mechanisms": dict(sorted(Counter(row["host"] or "other" for row in disagreements).items())), "disagreements": disagreements,
    })


def compare_l() -> None:
    independent = json.loads((V / "l_sensitivity_independent_validation.json").read_text())
    by_path = {row["log"]: row for row in independent["certificates"]}
    acquisition = json.loads((ROOT / "data/manifests/log_acquisition.json").read_text())["records"]
    path_to_key = {row["normalized_path"]: (row["canonical_upstream"], row["distribution"]) for row in acquisition if row.get("normalized_path")}
    primary = json.loads((ROOT / "data/derived/automatic_upl_labels_primary.json").read_text())
    sensitivity = json.loads((ROOT / "data/derived/automatic_upl_labels_posthoc_l_sensitivity.json").read_text())
    old = {(row["canonical_upstream"], row["distribution"]): row for row in primary["l"]}
    new = {(row["canonical_upstream"], row["distribution"]): row for row in sensitivity["l"]}
    records = []
    for path, cert in sorted(by_path.items()):
        key = path_to_key[path]
        changed = old[key]["state"] != new[key]["state"]
        generic = any(item.get("rule_id") == "L_GENERIC_ALL_CASES_PASSED_V1" for item in new[key].get("evidence", []))
        records.append({"canonical_upstream": key[0], "distribution": key[1], "log": path, "independent_reference_positive": cert["reference_positive"], "primary_state": old[key]["state"], "sensitivity_state": new[key]["state"], "sensitivity_changed": changed, "generic_rule_evidenced": generic, "agreement_on_generic_positive": cert["reference_positive"] if generic else None})
    generic_rows = [row for row in records if row["generic_rule_evidenced"]]
    write("l_sensitivity_production_vs_independent.json", {"schema_version": "1.0", "corpus_count": len(records), "generic_rule_positive_count": len(generic_rows), "generic_rule_independently_confirmed": sum(row["agreement_on_generic_positive"] is True for row in generic_rows), "generic_rule_not_confirmed": sum(row["agreement_on_generic_positive"] is False for row in generic_rows), "records": records})


if __name__ == "__main__":
    freeze = verify_freeze()
    compare_u(); compare_frame(); compare_l()
    write("production_comparison_provenance.json", {"schema_version": "1.0", "validation_outputs_freeze_sha256": sha(V / "validation_outputs_freeze.json"), "freeze_commit": "49466c0aa5eeaa96591af8051b782a6638f70f65", "production_inputs": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)} for path in [ROOT / "data/derived/automatic_upl_labels_primary.json", ROOT / "data/derived/automatic_upl_labels_posthoc_l_sensitivity.json", PHASE0 / "debian_sources.json", PHASE0 / "fedora_sources.json"]]})
