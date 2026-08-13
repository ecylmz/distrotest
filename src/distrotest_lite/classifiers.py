from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .common import config, ensure_layout, now_utc, write_json


U_RESOLVED = {"U_TEST_ENTRYPOINT_RESOLVED", "U_TEST_ASSETS_ONLY", "U_NO_TEST_CAPABILITY_RESOLVED"}
U_RULE_VERSION = "u-rules-v1.2.0-recursive-supported-build-surfaces"


def _read(path: Path, limit: int = 2_000_000, diagnostics: list[dict] | None = None) -> str:
    try:
        size = path.stat().st_size
        if size > limit:
            if diagnostics is not None:
                diagnostics.append({"path": str(path), "reason": "READ_LIMIT_EXCEEDED", "bytes": size, "limit": limit})
            # A bounded prefix can still establish positive evidence.  A
            # negative result with this diagnostic is left unresolved below.
            return path.read_bytes()[:limit].decode(errors="replace")
        return path.read_text(errors="replace")
    except OSError as exc:
        if diagnostics is not None:
            diagnostics.append({"path": str(path), "reason": "READ_ERROR", "detail": f"{type(exc).__name__}: {exc}"})
        return ""


def _files(tree: Path) -> list[Path]:
    excluded = {".git", "node_modules", "vendor", "target", ".tox", ".venv", "debian"}
    result = []
    for path in tree.rglob("*"):
        if path.is_file() and not excluded.intersection(path.relative_to(tree).parts):
            result.append(path)
    return result


def classify_u(tree: Path) -> dict:
    if not tree.exists():
        return {"state": "U_UNRESOLVED", "family": None, "rules": [], "reason": "UPSTREAM_SOURCE_UNAVAILABLE", "read_warnings": []}
    children = list(tree.iterdir())
    if len(children) == 1 and children[0].is_dir() and children[0].name.lower() not in {"test", "tests", "spec"}:
        tree = children[0]
    files = _files(tree)
    rel = {str(p.relative_to(tree)): p for p in files}
    evidence: list[dict] = []
    families: set[str] = set()
    read_warnings: list[dict] = []
    assets = any(re.search(r"(^|/)(tests?|spec)(/|$)|(?:^|/)test_[^/]+\.py$|_test\.go$", name, re.I) for name in rel)

    def read(path: Path) -> str:
        return _read(path, diagnostics=read_warnings)

    def hit(family: str, rule: str, names: list[str], pattern: str, *, recursive: bool = False) -> None:
        rx = re.compile(pattern, re.I | re.M)
        candidates = [
            (name, path)
            for name, path in sorted(rel.items())
            if name in names or (recursive and Path(name).name in names)
        ]
        for name, path in candidates:
            for number, line in enumerate(read(path).splitlines(), 1):
                code = line.split("#", 1)[0]
                match = rx.search(code)
                if match:
                    families.add(family)
                    evidence.append({"rule_id": rule, "family": family, "path": name, "line_start": number, "match": match.group(0)[:200]})
                    return

    hit(
        "autotools",
        "U_AUTOTOOLS_TEST_TARGET_V2",
        ["Makefile.am", "Makefile.in", "configure.ac", "configure.in"],
        r"^(?:TESTS|check_PROGRAMS|check_SCRIPTS)\s*(?:\+?=|:=)|^(?:check|test)(?:-[^:]*)?\s*:",
    )
    hit(
        "cmake",
        "U_CMAKE_CTEST_ROOT_V2",
        ["CMakeLists.txt"],
        r"\b(?:enable_testing|include\s*\(\s*CTest|add_test)\s*\(",
    )
    if "cmake" not in families:
        hit(
            "cmake",
            "U_CMAKE_CTEST_RECURSIVE_V2",
            ["CMakeLists.txt"],
            r"\b(?:add_test|gtest_discover_tests)\s*\(",
            recursive=True,
        )
    hit(
        "meson",
        "U_MESON_TEST_RECURSIVE_V2",
        ["meson.build"],
        r"(?<![A-Za-z_])test\s*\(",
        recursive=True,
    )
    hit("python", "U_PYTEST_CONFIG", ["pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini", "noxfile.py"], r"(?:pytest|unittest|\[tool\.pytest|\[pytest\]|commands\s*=\s*pytest|session\.run\([^\n]*pytest)")
    python_entrypoints = [name for name, path in rel.items() if name.endswith(".py") and re.search(r"\b(?:unittest\.main|pytest\.main)\s*\(", read(path))]
    if python_entrypoints:
        evidence.append({"rule_id": "U_PYTHON_LOCAL_ENTRYPOINT", "family": "python", "path": python_entrypoints[0], "match": "local test entrypoint"}); families.add("python")
    if "Cargo.toml" in rel and (assets or any("#[test]" in read(p) for n, p in rel.items() if n.endswith(".rs"))):
        evidence.append({"rule_id": "U_CARGO_STANDARD_TEST", "family": "cargo", "path": "Cargo.toml", "match": "Cargo standard test task"}); families.add("cargo")
    go_tests = [n for n in rel if n.endswith("_test.go")]
    if go_tests:
        evidence.append({"rule_id": "U_GO_TEST_FILES", "family": "go", "path": go_tests[0], "match": "go test standard entrypoint"}); families.add("go")
    if "pom.xml" in rel and (assets or any("src/test/" in n for n in rel)):
        evidence.append({"rule_id": "U_MAVEN_STANDARD_TEST", "family": "maven", "path": "pom.xml", "match": "Maven standard test lifecycle"}); families.add("maven")
    gradle = next((n for n in ("build.gradle", "build.gradle.kts") if n in rel), None)
    if gradle and (assets or "test" in read(rel[gradle])):
        evidence.append({"rule_id": "U_GRADLE_STANDARD_TEST", "family": "gradle", "path": gradle, "match": "Gradle test task"}); families.add("gradle")
    if "package.json" in rel:
        try:
            package = json.loads(read(rel["package.json"]))
            script = package.get("scripts", {}).get("test", "")
            if script and not re.search(r"no test specified|exit\s+1\b", script, re.I):
                evidence.append({"rule_id": "U_NODE_TEST_SCRIPT", "family": "node", "path": "package.json", "match": script[:200]}); families.add("node")
        except json.JSONDecodeError:
            return {"state": "U_UNRESOLVED", "family": "node", "rules": [], "reason": "OPAQUE_OR_INVALID_BUILD_CONFIG", "read_warnings": read_warnings}
    if evidence:
        return {"state": "U_TEST_ENTRYPOINT_RESOLVED", "family": "+".join(sorted(families)), "rules": evidence, "reason": None, "read_warnings": read_warnings}
    if read_warnings:
        return {"state": "U_UNRESOLVED", "family": "+".join(sorted(families)) or None, "rules": [], "reason": "BUILD_CONFIG_READ_INCOMPLETE", "read_warnings": read_warnings}
    supported = any(n in rel for n in ("Makefile.am", "configure.ac", "CMakeLists.txt", "meson.build", "pyproject.toml", "setup.cfg", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "package.json"))
    if assets:
        return {"state": "U_TEST_ASSETS_ONLY", "family": "+".join(sorted(families)) or None, "rules": [], "reason": "ASSETS_WITHOUT_RESOLVED_ENTRYPOINT", "read_warnings": []}
    if supported:
        return {"state": "U_NO_TEST_CAPABILITY_RESOLVED", "family": None, "rules": [], "reason": "SUPPORTED_BUILD_CONFIG_WITHOUT_TEST_CAPABILITY", "read_warnings": []}
    return {"state": "U_UNRESOLVED", "family": None, "rules": [], "reason": "UNSUPPORTED_TEST_FAMILY", "read_warnings": []}


RUNNERS = r"pytest|python\s+-m\s+unittest|ctest|meson\s+test|cargo\s+test|go\s+test|mvn\s+(?:test|verify)|gradle\w*\s+test|npm\s+test|yarn\s+test|pnpm\s+test|prove\b|rspec\b|phpunit\b|make\s+(?:check|test)\b"

P_RULE_VERSION = "p-rules-v1.1.0"
P_RULE_VERSION_PRESERVED = "p-rules-v1.0.0"


def _debian_test_override_bodies(text: str) -> list[dict[str, str]]:
    """Extract override_dh_auto_test bodies without treating headers as evidence."""
    headers = list(re.finditer(r"(?m)^override_dh_auto_test\s*:[^\n]*(?:\n|$)", text))
    target_header = re.compile(r"(?m)^[A-Za-z0-9_%.+@/$(){}-][^:=\n]*:\s*(?:#.*)?$")
    bodies = []
    for header in headers:
        following = target_header.search(text, header.end())
        end = following.start() if following else len(text)
        bodies.append({"header": header.group(0).rstrip(), "body": text[header.end():end]})
    return bodies


def _debian_override_semantics(body: str) -> str:
    """Return ACTIVE, DISABLED, or AMBIGUOUS for one test override body."""
    recipes = []
    for line in body.splitlines():
        if not line.startswith("\t"):
            continue
        command = re.sub(r"^\s*[@+\-]+", "", line[1:]).strip()
        if not command or command.startswith("#"):
            continue
        recipes.append(command)

    if not recipes:
        return "DISABLED"

    recipe_text = "\n".join(recipes)
    alternative_test_command = (
        r"(?:^|[\s;&|])(?:\./)?(?:[^\s;&|]*/)*(?:run[-_]?tests?|smoke[-_]?tests?|"
        r"tests?\.(?:py|pl|sh))(?=$|[\s;&|])|"
        r"\bpython\d*(?:\.\d+)?\s+(?:[^\s;&|]*/)*tests?[/._-][^\s;&|]*"
    )
    if re.search(rf"(?:\bdh_auto_test\b|{RUNNERS}|{alternative_test_command})", recipe_text, re.I | re.M):
        return "ACTIVE"

    def clear_noop(command: str) -> bool:
        command = re.sub(r"\s+#.*$", "", command).strip()
        if re.fullmatch(r"(?::|true|/bin/true)(?:\s*;)?", command):
            return True
        return bool(
            re.fullmatch(
                r"(?:echo|printf)\b[^\n]*(?:skip|disable|do nothing|not run|nocheck|tests?)[^\n]*",
                command,
                re.I,
            )
        )

    if all(clear_noop(command) for command in recipes):
        return "DISABLED"
    return "AMBIGUOUS"


def classify_p_v1_0_0(distribution: str, tree: Path, packaging_tree: Path | None = None) -> dict:
    """Preserved p-rules-v1.0.0 behavior for exact old-result reproduction."""
    return _classify_p(distribution, tree, packaging_tree, prospective_override_semantics=False)


def classify_p(distribution: str, tree: Path, packaging_tree: Path | None = None) -> dict:
    """Classify packaging intent with prospective p-rules-v1.1.0 semantics."""
    return _classify_p(distribution, tree, packaging_tree, prospective_override_semantics=True)


def _classify_p(
    distribution: str,
    tree: Path,
    packaging_tree: Path | None,
    *,
    prospective_override_semantics: bool,
) -> dict:
    labels: set[str] = set()
    evidence = []
    if distribution == "debian":
        rules = tree / "debian" / "rules"
        if not rules.exists():
            return {"labels": ["P_UNRESOLVED"], "reason": "PACKAGING_RECIPE_UNAVAILABLE", "evidence": []}
        text = _read(rules)
        if re.search(r"(?:eval\s|\$\(shell|define\s+.*test)", text, re.I):
            return {"labels": ["P_UNRESOLVED"], "reason": "OPAQUE_DYNAMIC_PACKAGING_CONSTRUCT", "evidence": []}
        disabled_pattern = r"(?:DEB_BUILD_OPTIONS[^\n]*nocheck|--(?:disable-tests?|without-tests?)|SKIP_TESTS?\s*=\s*1)"
        if not prospective_override_semantics:
            disabled_pattern = r"(?:DEB_BUILD_OPTIONS[^\n]*nocheck|override_dh_auto_test\s*:\s*(?:#.*)?$|--(?:disable-tests?|without-tests?)|SKIP_TESTS?\s*=\s*1)"
        declared_pattern = rf"(?:dh_auto_test\b|{RUNNERS})"
        if prospective_override_semantics:
            declared_pattern = rf"(?:dh_auto_test\b(?!\s*:)|{RUNNERS})"
        patterns = [
            ("P_TEST_EXPLICITLY_DISABLED", disabled_pattern),
            ("P_TEST_FILTERED_OR_SUBSETTED", r"(?:-k\s+\S+|--ignore(?:=|\s)|--exclude|TESTS?\s*=|PYTEST_ADDOPTS)"),
            ("P_TEST_DECLARED", declared_pattern),
            ("P_DOWNSTREAM_TEST_COMMAND_ADDED", rf"(?:override_dh_auto_(?:build|install)|execute_(?:before|after)_dh_auto_(?:build|install))[^:]*:[\s\S]{{0,500}}(?:{RUNNERS})"),
        ]
        for label, pattern in patterns:
            m = re.search(pattern, text, re.I | re.M)
            if m:
                labels.add(label); evidence.append({"label": label, "path": "debian/rules", "match": m.group(0)[:240]})
        if prospective_override_semantics:
            override_states = []
            for override in _debian_test_override_bodies(text):
                state = _debian_override_semantics(override["body"])
                override_states.append(state)
                captured = (override["header"] + "\n" + override["body"]).rstrip()[:240]
                if state == "ACTIVE":
                    labels.add("P_TEST_DECLARED")
                    evidence.append({"label": "P_TEST_DECLARED", "rule_id": "P_DEBIAN_ACTIVE_TEST_OVERRIDE", "path": "debian/rules", "match": captured})
                elif state == "DISABLED":
                    labels.add("P_TEST_EXPLICITLY_DISABLED")
                    evidence.append({"label": "P_TEST_EXPLICITLY_DISABLED", "rule_id": "P_DEBIAN_DISABLED_TEST_OVERRIDE", "path": "debian/rules", "match": captured})
            if "AMBIGUOUS" in override_states and "ACTIVE" not in override_states:
                return {"labels": ["P_UNRESOLVED"], "reason": "AMBIGUOUS_DH_AUTO_TEST_OVERRIDE", "evidence": evidence}
        if "P_DOWNSTREAM_TEST_COMMAND_ADDED" in labels:
            labels.add("P_TEST_RELOCATED_OR_EMBEDDED")
        if not labels:
            labels.add("P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED")
    else:
        base = packaging_tree or tree
        specs = sorted(base.glob("*.spec"))
        if len(specs) != 1:
            return {"labels": ["P_UNRESOLVED"], "reason": "PACKAGING_RECIPE_UNAVAILABLE" if not specs else "MULTIPLE_SPEC_FILES", "evidence": []}
        text = _read(specs[0])
        if re.search(r"%(?:lua|global)\s+.*(?:test|check).*(?:expand|lua:)", text, re.I):
            return {"labels": ["P_UNRESOLVED"], "reason": "OPAQUE_DYNAMIC_PACKAGING_CONSTRUCT", "evidence": []}
        check = re.search(r"(?ms)^%check\b(.*?)(?=^%(?:build|install|files|package|prep|changelog)\b|\Z)", text)
        if check:
            labels.add("P_TEST_DECLARED"); evidence.append({"label": "P_TEST_DECLARED", "path": specs[0].name, "match": check.group(0)[:240]})
        for label, pattern in [
            ("P_TEST_EXPLICITLY_DISABLED", r"(?:%bcond_with\s+tests?\b|--(?:disable-tests?|without-tests?)|-DskipTests|--no-tests|%global\s+with_tests?\s+0)"),
            ("P_TEST_FILTERED_OR_SUBSETTED", r"(?:-k\s+\S+|--ignore(?:=|\s)|--exclude|%global\s+.*(?:skip|exclude).*test)"),
        ]:
            m = re.search(pattern, text, re.I | re.M)
            if m:
                labels.add(label); evidence.append({"label": label, "path": specs[0].name, "match": m.group(0)[:240]})
        sections = list(re.finditer(r"(?m)^%(build|install)\b", text))
        for section in sections:
            end = re.search(r"(?m)^%(?:check|files|package|prep|build|install|changelog)\b", text[section.end():])
            body = text[section.start(): section.end() + (end.start() if end else len(text))]
            m = re.search(RUNNERS + r"|%(?:pytest|ctest|meson_test|cargo_test|mvn_build)\b", body, re.I)
            if m:
                labels.update(("P_TEST_DECLARED", "P_TEST_RELOCATED_OR_EMBEDDED")); evidence.append({"label": "P_TEST_RELOCATED_OR_EMBEDDED", "path": specs[0].name, "match": m.group(0)[:240]})
        if not labels:
            labels.add("P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED")
    return {"labels": sorted(labels), "reason": None, "evidence": evidence}


@dataclass(frozen=True)
class LRule:
    id: str
    family: str
    pattern: str
    count_group: int | None = None
    zero: bool = False


POSITIVE_RULES = [
    LRule("L_PYTEST_PASSED", "pytest", r"(?m)^=+\s*(\d+) passed(?:[,\s]|=)", 1),
    LRule("L_UNITTEST_RAN", "unittest", r"(?m)^Ran\s+(\d+)\s+tests?\b", 1),
    LRule("L_AUTOMAKE_PASS", "autotools", r"(?m)^PASS:\s+\S+"),
    LRule("L_CTEST_SUMMARY", "ctest", r"(?m)^100% tests passed,\s+\d+ tests failed out of\s+(\d+)\b", 1),
    # v1.2.2: a bare Meson `Ok:` summary is not sufficient because Meson
    # suites can contain lint or packaging-validation-only actions. Require a
    # completed named test/spec/unit/integration item in the same transcript.
    LRule("L_MESON_NAMED_TEST_OK", "meson", r"(?ms)^\s*\d+/\d+\s+[^\n]*(?:test|spec|unit|integration)[^\n]*\s+OK(?:\s+\S+)*\s*$.*?^\s*(?-i:Ok):\s+(\d+)\s*$", 1),
    LRule("L_CARGO_RESULT", "cargo", r"test result:\s+(?:ok|FAILED)\.\s+(\d+) passed", 1),
    LRule("L_GO_OK", "go", r"(?m)^ok\s+\S+\s+(?:\([^)]*\)\s+)?\d+(?:\.\d+)?s\s*$"),
    LRule("L_MAVEN_TESTS", "maven", r"Tests run:\s*(\d+)\s*,", 1),
    LRule("L_GRADLE_TESTS", "gradle", r"(?m)^\s*(\d+) tests? completed", 1),
    LRule("L_JEST_TESTS", "jest", r"(?m)^Tests:\s+.*?(\d+) passed", 1),
    LRule("L_MOCHA_PASSING", "mocha", r"(?m)^\s*(\d+) passing\b", 1),
    LRule("L_PERL_HARNESS", "perl", r"Files=\d+, Tests=(\d+),", 1),
    LRule("L_RSPEC_EXAMPLES", "rspec", r"(?m)^\s*(\d+) examples?,\s+\d+ failures?", 1),
    LRule("L_MINITEST_RUNS", "minitest", r"(?m)^\s*(\d+) runs,\s+(\d+) assertions", 1),
    LRule("L_PHPUNIT_OK", "phpunit", r"OK\s+\((\d+) tests?,", 1),
    LRule("L_CABAL_SUITE_PASS", "cabal", r"(?m)^Test suite\s+\S+:\s+PASS\s*$"),
]

ZERO_RULES = [
    LRule("L_PYTEST_ZERO", "pytest", r"(?mi)(?:collected 0 items|no tests ran)" , zero=True),
    LRule("L_CTEST_ZERO", "ctest", r"(?mi)(?:No tests were found|Total Tests:\s*0\s*$)", zero=True),
    LRule("L_CARGO_ZERO", "cargo", r"test result:\s+ok\.\s+0 passed;\s+0 failed;\s+0 ignored;\s+0 measured;\s+0 filtered out", zero=True),
    LRule("L_MAVEN_ZERO", "maven", r"Tests run:\s*0\s*,", zero=True),
    LRule("L_GO_ZERO", "go", r"(?m)^\?\s+\S+\s+\[no test files\]\s*$", zero=True),
    LRule("L_ALL_FILTERED", "generic", r"(?mi)(?:all tests? (?:were )?filtered out|0 tests? executed)" , zero=True),
]


def _pointer(text: str, match: re.Match, rule: LRule) -> dict:
    start_line = text.count("\n", 0, match.start()) + 1
    end_line = text.count("\n", 0, match.end()) + 1
    return {"rule_id": rule.id, "family": rule.family, "line_start": start_line, "line_end": end_line,
            "byte_start": len(text[:match.start()].encode()), "byte_end": len(text[:match.end()].encode()), "snippet": match.group(0)[:500]}


def classify_l_text(text: str, *, include_posthoc_success_rule: bool = False) -> dict:
    positives, zeros = [], []
    for rule in POSITIVE_RULES:
        for match in re.finditer(rule.pattern, text, re.I):
            if rule.count_group is not None and int(match.group(rule.count_group)) <= 0:
                continue
            positives.append(_pointer(text, match, rule))
    for rule in ZERO_RULES:
        for match in re.finditer(rule.pattern, text, re.I):
            zeros.append(_pointer(text, match, rule))
    # v1.1.0 prospective generic additions after the frozen v1.0.0 audit found
    # systematic visible forms. These require a completed transcript, not a
    # runner name or test-command invocation alone.
    r_rule = LRule("L_R_CHECK_TEST_FILE_OK", "r-check", r"(?ms)^\* checking tests \.\.\.\s*\n\s*Running [‘'`][^’'`\n]+[’'`]\s*\n\s*OK\s*$")
    for match in re.finditer(r_rule.pattern, text):
        positives.append(_pointer(text, match, r_rule))
    custom_rule = LRule("L_ASSERTION_TRANSCRIPT_PASS", "assertion-transcript", r"(?ms)^(?:\S*/)?test(?:/test)?\s*$.*?^test[_A-Za-z0-9-]*:\s*$.*?(?:^\s*\[PASS:\d+\].*$\n?){2,}")
    for match in re.finditer(custom_rule.pattern, text):
        positives.append(_pointer(text, match, custom_rule))
    tap_rule = LRule("L_TAP_NUMBERED_RESULTS", "tap", r"(?ms)^1\.\.(\d+)\s*$.*?^(?:not )?ok\s+\d+\b.*$")
    for match in re.finditer(tap_rule.pattern, text):
        if int(match.group(1)) > 0:
            positives.append(_pointer(text, match, tap_rule))
    phpt_rule = LRule("L_PHPT_NUMBERED_RESULT", "phpt", r"(?ms)^TEST\s+1/(\d+)\s+\[[^\n]+\]\s*$\n^(?:PASS|FAIL|XFAIL)\s+[^\n]+$")
    for match in re.finditer(phpt_rule.pattern, text):
        if int(match.group(1)) > 0:
            positives.append(_pointer(text, match, phpt_rule))
    dune_rule = LRule("L_DUNE_EXECUTED_TEST_BINARY", "dune", r"(?ms)^\s*dune runtest\b[^\n]*$.*?^\(cd\s+[^\n]*/tests?\s+&&\s+\./\S+\)(?:\s*$).*?^Test:\s+\S+.*$")
    for match in re.finditer(dune_rule.pattern, text):
        positives.append(_pointer(text, match, dune_rule))
    # Post-hoc measurement-corrected sensitivity only.  This generic form was
    # defined after the complete directional-case trace exposed an otherwise
    # missed nonzero success summary.  It is opt-in so the frozen primary rule
    # set and its labels remain reproducible.
    if include_posthoc_success_rule:
        all_cases_rule = LRule(
            "L_GENERIC_ALL_CASES_PASSED_V1",
            "generic-success-summary",
            r"(?m)^\s*(?:success:\s*)?all\s+([1-9]\d*)\s+(?:test\s+)?cases?\s+passed[.!]?\s*$",
            1,
        )
        for match in re.finditer(all_cases_rule.pattern, text, re.I):
            positives.append(_pointer(text, match, all_cases_rule))
    if positives:
        return {"state": "L_EXECUTION_EVIDENCED", "evidence": positives, "zero_evidence": zeros}
    if zeros:
        return {"state": "L_ZERO_TEST_EXECUTION_EVIDENCED", "evidence": zeros, "zero_evidence": zeros}
    return {"state": "L_NO_POSITIVE_EXECUTION_EVIDENCE", "evidence": [], "zero_evidence": []}


def classify_pilot() -> dict:
    root = ensure_layout()
    sources = json.loads((root / "derived" / "pilot_source_acquisition.json").read_text())["records"]
    logs = json.loads((root / "derived" / "pilot_log_acquisition.json").read_text())["records"]
    source_map = {(x["canonical_upstream"], x["distribution"]): x for x in sources}
    u_by_project = {}
    u_observations = []
    p_records = []
    pilot = json.loads((root / "manifests" / "pilot_40.json").read_text())
    for project in pilot["projects"]:
        cid = project["canonical_upstream"]
        project_u = []
        for distro in ("debian", "fedora"):
            rec = source_map.get((cid, distro))
            if not rec or rec["state"] != "AVAILABLE":
                u_result = {"state": "U_UNRESOLVED", "reason": "UPSTREAM_SOURCE_UNAVAILABLE", "family": None, "rules": []}
            else:
                u_result = classify_u(root / rec["tree"])
            u_observations.append({"canonical_upstream": cid, "distribution": distro, **u_result})
            project_u.append(u_result)
            if not rec or rec["state"] != "AVAILABLE":
                result = {"labels": ["P_UNRESOLVED"], "reason": "PACKAGING_RECIPE_UNAVAILABLE", "evidence": []}
            else:
                result = classify_p(distro, root / rec["tree"], root / rec.get("packaging_tree", rec["tree"]))
            p_records.append({"canonical_upstream": cid, "distribution": distro, **result})
        priority = {"U_TEST_ENTRYPOINT_RESOLVED": 3, "U_TEST_ASSETS_ONLY": 2, "U_NO_TEST_CAPABILITY_RESOLVED": 1, "U_UNRESOLVED": 0}
        u_by_project[cid] = max(project_u, key=lambda x: priority[x["state"]])
    l_records = []
    for log in logs:
        if log["state"] == "AVAILABLE":
            text = (root / log["normalized_path"]).read_text(errors="replace")
            result = classify_l_text(text)
        else:
            result = {"state": log["state"], "evidence": [], "zero_evidence": []}
        l_records.append({"canonical_upstream": log["canonical_upstream"], "distribution": log["distribution"], "source_log_sha256": log.get("raw_sha256"), "source_log": log.get("official_identifier"), **result})
    payload = {"classified_at": now_utc(), "rule_versions": config()["rules"], "u": u_by_project, "u_observations": u_observations, "p": p_records, "l": l_records}
    path = root / "derived" / "automatic_upl_labels.json"
    write_json(path, payload)
    write_json(root / "manifests" / "automatic_l_freeze.json", {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "frozen_at": now_utc(), "rule_version": config()["rules"]["l"]})
    return payload
