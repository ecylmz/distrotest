from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_analysis_inputs_cover_all_observations_once() -> None:
    labels = json.loads((ROOT / "data/derived/automatic_upl_labels_primary.json").read_text())
    for layer in ("u", "p", "l"):
        keys = [(row["canonical_upstream"], row["distribution"]) for row in labels[layer]]
        assert len(keys) == len(set(keys)) == 400


def test_authoritative_headline_counts() -> None:
    result = json.loads((ROOT / "results/authoritative/scientific_results_primary.json").read_text())
    assert result["retrievability"]["debian"]["positive_count"] == 71
    assert result["retrievability"]["fedora"]["positive_count"] == 121
    assert result["rq3"]["strict_resolved_projects"] == 53
    assert result["rq3"]["counts"] == {
        "both_evidenced": 17,
        "debian_only_evidenced": 4,
        "fedora_only_evidenced": 3,
        "neither_positive_evidence": 29,
        "one_or_both_unresolved": 117,
    }


def test_retained_validation_certificates_have_expected_scope() -> None:
    validation = ROOT / "data/validation"
    corrected = json.loads((validation / "u_corrected_production_assessment.json").read_text())
    assert (corrected["final_positive_count"], corrected["confirmed_count"], corrected["indeterminate_count"]) == (115, 93, 22)
    assert corrected["contradicted_count"] == 0
    frame = json.loads((validation / "frame_production_vs_independent.json").read_text())
    assert frame["production_retained_matched_project_count"] == 6950
    l_check = json.loads((validation / "l_sensitivity_production_vs_independent.json").read_text())
    assert l_check["corpus_count"] == 194
    assert l_check["generic_rule_positive_count"] == l_check["generic_rule_independently_confirmed"] == 1
