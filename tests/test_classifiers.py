from pathlib import Path

import pytest

from distrotest_lite.classifiers import classify_l_text, classify_p, classify_u


@pytest.mark.parametrize(("text", "state", "rule"), [
    ("===== 12 passed in 1.2s =====", "L_EXECUTION_EVIDENCED", "L_PYTEST_PASSED"),
    ("collected 12 items", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("collected 0 items", "L_ZERO_TEST_EXECUTION_EVIDENCED", "L_PYTEST_ZERO"),
    ("ctest -N\nTotal Tests: 8", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("No tests were found!!!", "L_ZERO_TEST_EXECUTION_EVIDENCED", "L_CTEST_ZERO"),
    ("100% tests passed, 0 tests failed out of 8", "L_EXECUTION_EVIDENCED", "L_CTEST_SUMMARY"),
    ("cargo test --no-run", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out", "L_EXECUTION_EVIDENCED", "L_CARGO_RESULT"),
    ("test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out", "L_ZERO_TEST_EXECUTION_EVIDENCED", "L_CARGO_ZERO"),
    ("make check", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("PASS: parser", "L_EXECUTION_EVIDENCED", "L_AUTOMAKE_PASS"),
    ("Tests run: 0, Failures: 0", "L_ZERO_TEST_EXECUTION_EVIDENCED", "L_MAVEN_ZERO"),
    ("Tests run: 7, Failures: 0", "L_EXECUTION_EVIDENCED", "L_MAVEN_TESTS"),
    ("? example/pkg [no test files]", "L_ZERO_TEST_EXECUTION_EVIDENCED", "L_GO_ZERO"),
    ("ok  example/pkg  0.123s", "L_EXECUTION_EVIDENCED", "L_GO_OK"),
    ("Tests: 2 skipped, 9 passed, 11 total", "L_EXECUTION_EVIDENCED", "L_JEST_TESTS"),
    ("0 tests completed", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("8 examples, 0 failures", "L_EXECUTION_EVIDENCED", "L_RSPEC_EXAMPLES"),
    ("OK (3 tests, 8 assertions)", "L_EXECUTION_EVIDENCED", "L_PHPUNIT_OK"),
    ("* checking tests ...\n  Running ‘simpleTests.R’\n OK", "L_EXECUTION_EVIDENCED", "L_R_CHECK_TEST_FILE_OK"),
    ("* checking tests ...\n  Running ‘simpleTests.R’", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("test/test\ntest_parser:\n  [PASS:12] value == 1\n  [PASS:13] other == 2\n", "L_EXECUTION_EVIDENCED", "L_ASSERTION_TRANSCRIPT_PASS"),
    ("configure test\n[PASS:12] compiler available\n", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("perl test.pl\n1..2\nok 1\nnot ok 2", "L_EXECUTION_EVIDENCED", "L_TAP_NUMBERED_RESULTS"),
    ("1..0", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("TEST 1/3 [tests/a.phpt]\nPASS behavior [tests/a.phpt]", "L_EXECUTION_EVIDENCED", "L_PHPT_NUMBERED_RESULT"),
    ("TEST 1/3 [tests/a.phpt]", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("dune runtest -p p\n(cd _build/default/tests && ./case.exe)\nTest: behavior", "L_EXECUTION_EVIDENCED", "L_DUNE_EXECUTED_TEST_BINARY"),
    ("dune runtest -p p", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("Ok: 7", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("1/1 suite / unit-tests OK 0.03s\n\nOk: 1", "L_EXECUTION_EVIDENCED", "L_MESON_NAMED_TEST_OK"),
    ("1/1 validate-metainfo OK 0.03s\n\nOk: 1", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
    ("OK: 181 passed", "L_NO_POSITIVE_EXECUTION_EVIDENCE", None),
])
def test_l_fixtures(text, state, rule):
    result = classify_l_text(text)
    assert result["state"] == state
    assert (result["evidence"][0]["rule_id"] if result["evidence"] else None) == rule


def test_u_cmake_positive(tmp_path: Path):
    (tmp_path / "CMakeLists.txt").write_text("enable_testing()\nadd_test(NAME x COMMAND x)")
    assert classify_u(tmp_path)["state"] == "U_TEST_ENTRYPOINT_RESOLVED"


@pytest.mark.parametrize(
    ("root_name", "child_name", "root_text", "child_text", "rule_id"),
    [
        ("CMakeLists.txt", "tests/CMakeLists.txt", "add_subdirectory(tests)\n", "add_test(NAME smoke COMMAND smoke)\n", "U_CMAKE_CTEST_RECURSIVE_V2"),
        ("meson.build", "tests/meson.build", "subdir('tests')\n", "test('smoke', smoke)\n", "U_MESON_TEST_RECURSIVE_V2"),
    ],
)
def test_u_recursive_supported_build_surface(
    tmp_path: Path, root_name: str, child_name: str, root_text: str, child_text: str, rule_id: str
):
    (tmp_path / root_name).write_text(root_text)
    child = tmp_path / child_name
    child.parent.mkdir()
    child.write_text(child_text)
    result = classify_u(tmp_path)
    assert result["state"] == "U_TEST_ENTRYPOINT_RESOLVED"
    assert result["rules"][0]["rule_id"] == rule_id
    assert result["rules"][0]["path"] == child_name


@pytest.mark.parametrize("target", ["test:", "test-strict: install", "check-testsuite: lib"])
def test_u_make_test_target_variants(tmp_path: Path, target: str):
    (tmp_path / "Makefile.am").write_text(f"{target}\n\t./smoke\n")
    result = classify_u(tmp_path)
    assert result["state"] == "U_TEST_ENTRYPOINT_RESOLVED"
    assert result["rules"][0]["rule_id"] == "U_AUTOTOOLS_TEST_TARGET_V2"


@pytest.mark.parametrize(
    ("filename", "text"),
    [
        ("CMakeLists.txt", "# add_test(NAME docs COMMAND docs)\n"),
        ("meson.build", "# test('docs', docs)\n"),
        ("Makefile.am", "# test: documentation only\n"),
    ],
)
def test_u_recursive_rule_rejects_commented_negatives(tmp_path: Path, filename: str, text: str):
    (tmp_path / filename).write_text(text)
    assert classify_u(tmp_path)["state"] == "U_NO_TEST_CAPABILITY_RESOLVED"


def test_u_recursive_rule_excludes_vendor_subproject(tmp_path: Path):
    (tmp_path / "CMakeLists.txt").write_text("project(example)\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor/CMakeLists.txt").write_text("add_test(NAME vendored COMMAND vendored)\n")
    assert classify_u(tmp_path)["state"] == "U_NO_TEST_CAPABILITY_RESOLVED"


def test_u_nested_enable_testing_alone_is_not_an_entrypoint(tmp_path: Path):
    (tmp_path / "CMakeLists.txt").write_text("add_subdirectory(clients)\n")
    (tmp_path / "clients").mkdir()
    (tmp_path / "clients/CMakeLists.txt").write_text("enable_testing()\n")
    assert classify_u(tmp_path)["state"] == "U_NO_TEST_CAPABILITY_RESOLVED"


def test_u_assets_only(tmp_path: Path):
    (tmp_path / "tests").mkdir(); (tmp_path / "tests" / "case.xyz").write_text("data")
    assert classify_u(tmp_path)["state"] == "U_TEST_ASSETS_ONLY"


def test_u_opaque(tmp_path: Path):
    (tmp_path / "waf").write_text("custom")
    assert classify_u(tmp_path)["state"] == "U_UNRESOLVED"


def test_p_debian_embedded(tmp_path: Path):
    (tmp_path / "debian").mkdir(); (tmp_path / "debian" / "rules").write_text("override_dh_auto_build:\n\tpytest -q\n")
    labels = classify_p("debian", tmp_path)["labels"]
    assert "P_TEST_DECLARED" in labels and "P_TEST_RELOCATED_OR_EMBEDDED" in labels


def test_p_debian_disable(tmp_path: Path):
    (tmp_path / "debian").mkdir(); (tmp_path / "debian" / "rules").write_text("override_dh_auto_test:\n\t# disabled\n")
    labels = classify_p("debian", tmp_path)["labels"]
    assert "P_TEST_EXPLICITLY_DISABLED" in labels
    assert "P_TEST_DECLARED" not in labels


@pytest.mark.parametrize(("body", "required", "forbidden", "reason"), [
    ("", "P_TEST_EXPLICITLY_DISABLED", "P_TEST_DECLARED", None),
    ("\t# tests intentionally disabled\n\t@echo 'tests disabled by policy'\n", "P_TEST_EXPLICITLY_DISABLED", "P_TEST_DECLARED", None),
    ("\tdh_auto_test\n", "P_TEST_DECLARED", "P_TEST_EXPLICITLY_DISABLED", None),
    ("\tTERM=xterm dh_auto_test\n", "P_TEST_DECLARED", "P_TEST_EXPLICITLY_DISABLED", None),
    ("\tdh_auto_test -- --verbose\n", "P_TEST_DECLARED", "P_TEST_EXPLICITLY_DISABLED", None),
    ("\tpytest -q\n", "P_TEST_DECLARED", "P_TEST_EXPLICITLY_DISABLED", None),
    ("ifeq (,$(filter nocheck,$(DEB_BUILD_OPTIONS)))\n\tdh_auto_test\nendif\n", "P_TEST_DECLARED", "P_TEST_EXPLICITLY_DISABLED", None),
    ("ifneq (,$(filter nocheck,$(DEB_BUILD_OPTIONS)))\n\t@echo 'skip tests under nocheck'\nendif\n", "P_TEST_EXPLICITLY_DISABLED", "P_TEST_DECLARED", None),
    ("\trm -f build/test-stamp\n", "P_UNRESOLVED", "P_TEST_EXPLICITLY_DISABLED", "AMBIGUOUS_DH_AUTO_TEST_OVERRIDE"),
    ("\tcommand=\"$${TEST_COMMAND}\"; eval \"$$command\"\n", "P_UNRESOLVED", "P_TEST_EXPLICITLY_DISABLED", "OPAQUE_DYNAMIC_PACKAGING_CONSTRUCT"),
])
def test_p_debian_override_semantics(tmp_path: Path, body: str, required: str, forbidden: str, reason: str | None):
    (tmp_path / "debian").mkdir()
    (tmp_path / "debian" / "rules").write_text(f"override_dh_auto_test:\n{body}")
    result = classify_p("debian", tmp_path)
    assert required in result["labels"]
    assert forbidden not in result["labels"]
    assert result["reason"] == reason


def test_p_fedora_check(tmp_path: Path):
    (tmp_path / "x.spec").write_text("%build\nmake\n%check\n%pytest\n%files\n")
    assert "P_TEST_DECLARED" in classify_p("fedora", tmp_path, tmp_path)["labels"]


def test_p_fedora_opaque(tmp_path: Path):
    (tmp_path / "x.spec").write_text("%global runtest %{lua: print('x')}\n")
    assert classify_p("fedora", tmp_path, tmp_path)["labels"] == ["P_UNRESOLVED"]
