"""Validator B: parser-led static semantic inspection, separate from production."""

from __future__ import annotations

import configparser
import hashlib
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _in_scope(path: Path, root: Path) -> bool:
    return not ({part.lower() for part in path.relative_to(root).parts} & {"debian", ".pc", ".git", "vendor", "node_modules", "target", ".tox", ".venv"})


def _lines(path: Path, pattern: re.Pattern[str]) -> list[dict]:
    found = []
    for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if pattern.search(line):
            found.append({"file": path.name, "line_start": number, "line_end": number, "construct": line.strip()[:240]})
    return found


def _assets(root: Path) -> list[str]:
    values = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not _in_scope(path, root):
            continue
        rel = relative.as_posix()
        parts = {p.lower() for p in relative.parts[:-1]}
        name = path.name.lower()
        if parts & {"test", "tests", "t", "spec", "specs", "testing"} or name.startswith("test_") or name.endswith(("_test.py", "_test.go", "_test.rs", "_spec.rb", ".t", ".phpt")):
            values.append(rel)
    return values[:200]


def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(errors="replace"))
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _xml(path: Path) -> ET.Element | None:
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None


def _scan(root: Path) -> tuple[list[str], list[dict], list[dict]]:
    """Return examined surfaces, positive evidence, and failed surfaces."""
    surfaces: list[str] = []
    evidence: list[dict] = []
    failures: list[dict] = []

    cmake = root / "CMakeLists.txt"
    if cmake.exists():
        surfaces.append("cmake")
        text = cmake.read_text(errors="replace")
        # Tokenise command heads, ignoring comment-only lines. This is not the
        # production substring/regex table and requires an actual CMake call.
        for number, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
            if match and match.group(1).lower() in {"add_test", "ctest_test", "gtest_discover_tests"}:
                evidence.append({"file": "CMakeLists.txt", "line_start": number, "line_end": number, "construct": "CMake test command", "parser": "cmake-command-lexer"})
        # Test commands frequently live in included subdirectories.
        for child in sorted(path for path in root.rglob("CMakeLists.txt") if _in_scope(path, root)):
            if child == cmake:
                continue
            for item in _lines(child, re.compile(r"^\s*(?:add_test|gtest_discover_tests)\s*\(", re.I)):
                item["file"] = child.relative_to(root).as_posix(); item["parser"] = "cmake-command-lexer"; evidence.append(item)

    meson = root / "meson.build"
    if meson.exists():
        surfaces.append("meson")
        for child in sorted(path for path in root.rglob("meson.build") if _in_scope(path, root)):
            for item in _lines(child, re.compile(r"^\s*(?:test|benchmark)\s*\(")):
                item["file"] = child.relative_to(root).as_posix(); item["parser"] = "meson-call-lexer"; evidence.append(item)

    go = root / "go.mod"
    if go.exists():
        surfaces.append("go")
        for child in sorted(path for path in root.rglob("*_test.go") if _in_scope(path, root)):
            for item in _lines(child, re.compile(r"^\s*func\s+(?:Test|Example|Benchmark)[A-Za-z0-9_]*\s*\(")):
                item["file"] = child.relative_to(root).as_posix(); item["parser"] = "go-declaration-lexer"; evidence.append(item)

    cargo = root / "Cargo.toml"
    if cargo.exists():
        surfaces.append("cargo")
        data = _toml(cargo)
        if not data:
            failures.append({"surface": "cargo", "reason": "TOML_PARSE_FAILURE"})
        for child in sorted(path for path in root.rglob("*.rs") if _in_scope(path, root)):
            for item in _lines(child, re.compile(r"^\s*#\s*\[\s*test\s*\]")):
                item["file"] = child.relative_to(root).as_posix(); item["parser"] = "rust-attribute-lexer"; evidence.append(item)
        for target in data.get("test", []) if isinstance(data.get("test"), list) else []:
            evidence.append({"file": "Cargo.toml", "line_start": None, "line_end": None, "construct": f"declared Cargo test target {target.get('name', '')}", "parser": "tomllib"})

    python_configs = [root / name for name in ("pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini") if (root / name).exists()]
    if python_configs:
        surfaces.append("python")
        for path in python_configs:
            if path.suffix == ".toml":
                data = _toml(path)
                if not data:
                    failures.append({"surface": "python", "reason": f"TOML_PARSE_FAILURE:{path.name}"})
                pytest_cfg = data.get("tool", {}).get("pytest", {}) if isinstance(data.get("tool"), dict) else {}
                if pytest_cfg:
                    evidence.append({"file": path.name, "line_start": None, "line_end": None, "construct": "structured pytest configuration", "parser": "tomllib"})
            else:
                parser = configparser.ConfigParser(interpolation=None)
                try:
                    parser.read(path, encoding="utf-8")
                    if any(section.lower().startswith(("pytest", "tool:pytest", "testenv")) for section in parser.sections()):
                        evidence.append({"file": path.name, "line_start": None, "line_end": None, "construct": "structured Python test configuration", "parser": "configparser"})
                except configparser.Error:
                    failures.append({"surface": "python", "reason": f"INI_PARSE_FAILURE:{path.name}"})
        for child in sorted(path for path in root.rglob("*.py") if _in_scope(path, root)):
            for item in _lines(child, re.compile(r"\b(?:pytest|unittest)\.main\s*\(")):
                item["file"] = child.relative_to(root).as_posix(); item["parser"] = "python-call-lexer"; evidence.append(item)

    pom = root / "pom.xml"
    if pom.exists():
        surfaces.append("maven")
        tree = _xml(pom)
        if tree is None:
            failures.append({"surface": "maven", "reason": "XML_PARSE_FAILURE"})
        elif any((root / "src/test").rglob("*")):
            evidence.append({"file": "pom.xml", "line_start": None, "line_end": None, "construct": "Maven standard test source tree", "parser": "xml.etree+path-structure"})

    gradle = next((root / name for name in ("build.gradle", "build.gradle.kts") if (root / name).exists()), None)
    if gradle is not None:
        surfaces.append("gradle")
        text = gradle.read_text(errors="replace")
        explicit = re.compile(r"(?:^|\s)(?:task\s+test\b|tasks\.(?:named|register)\s*\(\s*[\"']test[\"']|test\s*\{)")
        java_plugin = re.compile(r"(?:id\s*[\( ]\s*[\"'](?:java|java-library)[\"']|apply\s+plugin\s*:\s*[\"']java[\"'])")
        for number, line in enumerate(text.splitlines(), 1):
            code = line.split("//", 1)[0]
            if explicit.search(code):
                evidence.append({"file": gradle.name, "line_start": number, "line_end": number, "construct": code.strip()[:240], "parser": "gradle-task-lexer"})
            elif java_plugin.search(code) and (root / "src/test").is_dir():
                evidence.append({"file": gradle.name, "line_start": number, "line_end": number, "construct": "Gradle Java plugin with standard test source set", "parser": "gradle-plugin-lexer+path-structure"})

    package = root / "package.json"
    if package.exists():
        surfaces.append("javascript")
        try:
            data = json.loads(package.read_text(errors="replace"))
            script = data.get("scripts", {}).get("test")
            if script and "no test specified" not in str(script).lower():
                evidence.append({"file": "package.json", "line_start": None, "line_end": None, "construct": f"test script: {script}", "parser": "json"})
        except json.JSONDecodeError:
            failures.append({"surface": "javascript", "reason": "JSON_PARSE_FAILURE"})

    makefiles = [path for path in (root / "Makefile.am", root / "Makefile.in", root / "configure.ac", root / "configure.in") if path.exists()]
    if makefiles:
        surfaces.append("make-autotools")
        target = re.compile(r"^(check|test)(?:-[^:]*)?\s*:(?![=])")
        declarations = re.compile(r"^(?:TESTS|check_PROGRAMS|check_SCRIPTS)\s*(?:\+?=|:=)\s*(\S.*)$")
        for path in makefiles:
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                code = line.split("#", 1)[0].rstrip()
                if target.match(code) or declarations.match(code):
                    evidence.append({"file": path.name, "line_start": number, "line_end": number, "construct": code[:240], "parser": "make-target-parser"})

    return sorted(set(surfaces)), evidence, failures


def validate_case(record: dict, root: Path) -> dict:
    source = root / record["source_tree"]
    surfaces, evidence, failures = _scan(source)
    assets = _assets(source)
    complete = bool(surfaces) and not failures
    if evidence:
        state = "U_TEST_ENTRYPOINT_RESOLVED"
        status = "RESOLVED_STRUCTURED_POSITIVE"
        reason = "A parser-led supported-surface scan found an executable test convention or declared target."
    elif not complete:
        state = "VALIDATION_INDETERMINATE"
        status = "VALIDATION_INDETERMINATE"
        reason = "No positive was found, but no supported surface was available or a structured parse failed."
    elif assets:
        state = "U_TEST_ASSETS_ONLY"
        status = "RESOLVED_STRUCTURED_ZERO_WITH_ASSETS"
        reason = "All detected supported surfaces were parsed without an executable entrypoint, and test-like assets remain."
    else:
        state = "U_NO_TEST_CAPABILITY_RESOLVED"
        status = "RESOLVED_STRUCTURED_ZERO_NO_ASSETS"
        reason = "All detected supported surfaces were parsed without an executable entrypoint or test-like assets."
    return {
        "case_id": record["case_id"],
        "source_sha256": record["source_tree_certificate"]["sha256"],
        "validation_backend": "validator_b_structured_v1.1.1-contract-aligned",
        "validation_status": status,
        "reference_state": state,
        "family": surfaces,
        "evidence": evidence,
        "resolved_entrypoint": evidence[0]["construct"] if evidence else None,
        "reason": reason,
        "coverage": [{"surface": item, "examined": True} for item in surfaces],
        "absence_checklist_complete": complete,
        "asset_examples": assets[:20],
        "limitations": [item["reason"] for item in failures] or ["Static semantics can establish supported declarations but do not prove runtime success."],
    }
