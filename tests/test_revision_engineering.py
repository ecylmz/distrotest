from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

from distrotest_lite.classifiers import classify_l_text, classify_u
from distrotest_lite.full_study import extract_primary_source_archive, source_archive_candidates
from distrotest_lite.repositories import canonical_url
from distrotest_lite.revision_analysis import stratified_project_bootstrap, stratified_ratio_fpc, weighted_ratio


def _tar(path: Path, filename: str = "README", content: bytes = b"source\n") -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(filename)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))


def test_gitlab_nested_project_identity_and_reserved_view_suffix() -> None:
    root, method = canonical_url("https://gitlab.com/ubports/development/core/gsettings-qt.git")
    tree, _ = canonical_url("https://gitlab.com/ubports/development/core/gsettings-qt/-/tree/main")
    assert method == "EXACT_CANONICAL_FORGE_URL"
    assert root == tree == "gitlab.com/ubports/development/core/gsettings-qt"


def test_non_gitlab_forge_still_uses_owner_project_identity() -> None:
    identity, _ = canonical_url("https://github.com/pallets/flask/tree/main")
    assert identity == "github.com/pallets/flask"


def test_sourcehut_identity_includes_owner_and_repository() -> None:
    first, _ = canonical_url("https://git.sr.ht/~sircmpwn/scdoc.git")
    second, _ = canonical_url("https://git.sr.ht/~sircmpwn/wev/tree/main")
    assert first == "git.sr.ht/~sircmpwn/scdoc"
    assert second == "git.sr.ht/~sircmpwn/wev"
    assert first != second


def test_source_archive_candidates_are_sorted_and_role_source0(tmp_path: Path) -> None:
    _tar(tmp_path / "z-aux.tar.gz")
    _tar(tmp_path / "a-primary.tar.gz")
    rows = source_archive_candidates(tmp_path, "a-primary.tar.gz")
    assert [row["name"] for row in rows] == ["a-primary.tar.gz", "z-aux.tar.gz"]
    assert [row["role"] for row in rows] == ["PRIMARY_SOURCE0", "AUXILIARY_SOURCE"]


def test_rubygem_extraction_uses_nested_data_payload(tmp_path: Path) -> None:
    nested = io.BytesIO()
    with tarfile.open(fileobj=nested, mode="w:gz") as payload:
        content = b"RSpec.describe('x') {}\n"
        info = tarfile.TarInfo("spec/example_spec.rb")
        info.size = len(content)
        payload.addfile(info, io.BytesIO(content))
    gem = tmp_path / "example.gem"
    with tarfile.open(gem, "w") as outer:
        data = nested.getvalue()
        info = tarfile.TarInfo("data.tar.gz")
        info.size = len(data)
        outer.addfile(info, io.BytesIO(data))
    destination = tmp_path / "tree"
    assert extract_primary_source_archive(gem, destination) == "RUBYGEM_DATA_TAR"
    assert (destination / "spec" / "example_spec.rb").read_text() == "RSpec.describe('x') {}\n"


def test_zip_primary_source_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("project/CMakeLists.txt", "enable_testing()\n")
    destination = tmp_path / "tree"
    assert extract_primary_source_archive(archive, destination) == "ZIP"
    assert (destination / "project" / "CMakeLists.txt").exists()


def test_oversized_u_configuration_is_not_silently_treated_as_empty(tmp_path: Path) -> None:
    (tmp_path / "CMakeLists.txt").write_bytes(b"#" * 2_000_001)
    result = classify_u(tmp_path)
    assert result["state"] == "U_UNRESOLVED"
    assert result["reason"] == "BUILD_CONFIG_READ_INCOMPLETE"
    assert result["read_warnings"][0]["reason"] == "READ_LIMIT_EXCEEDED"


def test_posthoc_generic_success_rule_is_opt_in_and_requires_nonzero_count() -> None:
    text = "All 521 test cases passed.\n"
    assert classify_l_text(text)["state"] == "L_NO_POSITIVE_EXECUTION_EVIDENCE"
    revised = classify_l_text(text, include_posthoc_success_rule=True)
    assert revised["state"] == "L_EXECUTION_EVIDENCED"
    assert revised["evidence"][0]["rule_id"] == "L_GENERIC_ALL_CASES_PASSED_V1"
    assert classify_l_text("All 0 test cases passed.", include_posthoc_success_rule=True)["state"] == "L_NO_POSITIVE_EXECUTION_EVIDENCE"


def test_posthoc_generic_success_rule_rejects_unbounded_claims() -> None:
    for text in ("All cases passed.", "521 test cases", "All 12 cases failed.", "All test cases passed."):
        assert classify_l_text(text, include_posthoc_success_rule=True)["state"] == "L_NO_POSITIVE_EXECUTION_EVIDENCE"


def _synthetic_sample() -> dict:
    return {
        "projects": [
            {"canonical_upstream": "a", "stratum": "C2V", "stratum_population": 10, "design_weight": 5.0},
            {"canonical_upstream": "b", "stratum": "C2V", "stratum_population": 10, "design_weight": 5.0},
            {"canonical_upstream": "c", "stratum": "NON_C2V", "stratum_population": 20, "design_weight": 10.0},
            {"canonical_upstream": "d", "stratum": "NON_C2V", "stratum_population": 20, "design_weight": 10.0},
        ]
    }


def test_weighted_ratio_uses_stratum_design_weights() -> None:
    sample = _synthetic_sample()
    project = {row["canonical_upstream"]: row for row in sample["projects"]}
    assert weighted_ratio(list(project), project, lambda identity: identity in {"a", "c"}, lambda identity: True) == 0.5
    assert weighted_ratio(list(project), project, lambda identity: identity == "a", lambda identity: identity in {"a", "b"}) == 0.5


def test_stratified_bootstrap_is_deterministic_and_retains_stratum_sizes() -> None:
    sample = _synthetic_sample()
    observed = []

    def statistic(identities: list[str]) -> float:
        observed.append(identities)
        return identities.count("a") / len(identities)

    first = stratified_project_bootstrap(sample, statistic, seed=42, replicates=20)
    second = stratified_project_bootstrap(sample, lambda identities: identities.count("a") / len(identities), seed=42, replicates=20)
    assert first == second
    assert all(len(identities) == 4 for identities in observed)
    assert all(sum(identity in {"a", "b"} for identity in identities) == 2 for identities in observed)


def test_fpc_ratio_sensitivity_returns_bounded_interval() -> None:
    sample = _synthetic_sample()
    result = stratified_ratio_fpc(sample, lambda identity: identity in {"a", "c"}, lambda identity: True)
    assert result["estimate"] == 0.5
    assert result["standard_error"] > 0
    assert 0 <= result["normal_ci"][0] <= result["normal_ci"][1] <= 1
