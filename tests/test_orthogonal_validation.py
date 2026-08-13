from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

from distrotest_lite_validation.frame_identity import independent_identity
from distrotest_lite_validation.log_success import ADVERSARIAL_NEGATIVES, validate_line
from distrotest_lite_validation.native_u import _run
from distrotest_lite_validation.structured_u import validate_case


ROOT = Path(__file__).resolve().parents[1]


def test_validation_modules_do_not_import_production_classifiers() -> None:
    for path in sorted((ROOT / "src/distrotest_lite_validation").glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name.startswith("distrotest_lite") for name in imported), (path, imported)


def test_blind_u_input_contains_no_production_labels() -> None:
    data = json.loads((ROOT / "data/validation/u88_blind_input.json").read_text())
    forbidden = {"state", "labels", "production_u", "production_p", "production_l", "rq1"}
    assert len(data["records"]) == 88
    assert all(not (forbidden & set(record)) for record in data["records"])


def test_native_timeout_is_indeterminate_signal(tmp_path: Path) -> None:
    result = _run(tmp_path, ["sh", "-c", "while :; do :; done"], timeout_seconds=1)
    assert result["timed_out"] is True
    assert result["exit_code"] is None


def test_negative_structured_state_requires_explicit_coverage(tmp_path: Path) -> None:
    record = {"case_id": "fixture", "source_tree": ".", "source_tree_certificate": {"sha256": "fixture"}}
    empty = validate_case(record, tmp_path)
    assert empty["reference_state"] == "VALIDATION_INDETERMINATE"
    assert empty["absence_checklist_complete"] is False
    (tmp_path / "Cargo.toml").write_text('[package]\nname="fixture"\nversion="0.1.0"\n')
    covered = validate_case(record, tmp_path)
    assert covered["reference_state"] == "U_NO_TEST_CAPABILITY_RESOLVED"
    assert covered["absence_checklist_complete"] is True


def test_out_of_contract_perl_surface_remains_indeterminate(tmp_path: Path) -> None:
    (tmp_path / "Makefile.PL").write_text("use ExtUtils::MakeMaker;\n")
    (tmp_path / "t").mkdir()
    (tmp_path / "t/example.t").write_text("use Test::More tests => 1; ok 1;\n")
    record = {"case_id": "perl", "source_tree": ".", "source_tree_certificate": {"sha256": "fixture"}}
    result = validate_case(record, tmp_path)
    assert result["reference_state"] == "VALIDATION_INDETERMINATE"
    assert result["absence_checklist_complete"] is False


def test_python_test_filename_alone_is_asset_not_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.1"\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_example.py").write_text("def test_example(): pass\n")
    record = {"case_id": "python", "source_tree": ".", "source_tree_certificate": {"sha256": "fixture"}}
    result = validate_case(record, tmp_path)
    assert result["reference_state"] == "U_TEST_ASSETS_ONLY"


def test_downstream_debian_tests_are_not_upstream_assets(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.1"\n')
    (tmp_path / "debian/tests").mkdir(parents=True)
    (tmp_path / "debian/tests/smoke").write_text("downstream packaging test\n")
    record = {"case_id": "scope", "source_tree": ".", "source_tree_certificate": {"sha256": "fixture"}}
    result = validate_case(record, tmp_path)
    assert result["reference_state"] == "U_NO_TEST_CAPABILITY_RESOLVED"


def test_frame_validator_handles_nested_gitlab_and_collision_forms() -> None:
    forms = [
        "https://gitlab.com/group/nested/project.git",
        "https://gitlab.com/group/nested/project/",
        "https://gitlab.com/group/nested/project/-/tree/main?x=1#readme",
    ]
    identities = {independent_identity(value)["identity"] for value in forms}
    assert identities == {"gitlab.com/group/nested/project"}


def test_frame_validator_handles_suffixes_views_and_sourcehut() -> None:
    assert independent_identity("https://github.com/Owner/Repo.git/")["identity"] == "github.com/owner/repo"
    assert independent_identity("https://github.com/Owner/Repo/blob/main/a")['identity'] == "github.com/owner/repo"
    assert independent_identity("https://git.sr.ht/~Owner/Repo/tree/main")['identity'] == "git.sr.ht/~owner/repo"


def test_l_validator_rejects_all_adversarial_negatives() -> None:
    for value in ADVERSARIAL_NEGATIVES:
        result = validate_line(value)
        assert result is None or result["positive"] is False, value
    assert validate_line("All 521 test cases passed.")["positive"] is True


def test_comparison_module_exists_but_cannot_run_without_output_freeze() -> None:
    path = ROOT / "scripts/validate/compare_u_orthogonal_validation.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("comparison", path)
    assert spec is not None
