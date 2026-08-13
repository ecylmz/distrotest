"""State-specific U validation over independently recoverable positive evidence.

This module is isolated from ``distrotest_lite`` and never consumes production
rule identifiers, trigger text, evidence snippets, P/L labels, or RQ outcomes.
It composes two pre-existing independent evidence paths after generic archive-
wrapper normalization and maps unresolved execution to indeterminate evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .native_u import validate_case as validate_native
from .structured_u import validate_case as validate_structured


EXCLUDED_PARTS = {"debian", ".pc", ".git", "vendor", "node_modules", "target", ".tox", ".venv"}
SUPPORTED_ROOT_FILES = {
    "CMakeLists.txt", "meson.build", "go.mod", "Cargo.toml", "pyproject.toml",
    "setup.cfg", "pytest.ini", "tox.ini", "pom.xml", "build.gradle",
    "build.gradle.kts", "package.json", "Makefile.am", "Makefile.in",
    "configure.ac", "configure.in",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_certificate(tree: Path) -> dict:
    digest = hashlib.sha256()
    files = 0
    bytes_total = 0
    for path in sorted(tree.rglob("*"), key=lambda item: item.relative_to(tree).as_posix()):
        relative = path.relative_to(tree).as_posix()
        if path.is_symlink():
            payload = os.readlink(path).encode()
            kind = "symlink"
        elif path.is_file():
            payload = bytes.fromhex(sha256(path))
            kind = "file"
            files += 1
            bytes_total += path.stat().st_size
        else:
            continue
        digest.update(kind.encode() + b"\0" + relative.encode() + b"\0" + payload + b"\n")
    return {"sha256": digest.hexdigest(), "regular_files": files, "regular_file_bytes": bytes_total}


def project_root(source: Path) -> Path:
    """Remove generic single-directory archive wrappers without case overrides."""
    current = source
    for _ in range(4):
        if any((current / name).is_file() for name in SUPPORTED_ROOT_FILES):
            break
        entries = sorted(path for path in current.iterdir() if path.name not in {"__MACOSX"})
        visible_files = [path for path in entries if path.is_file() and not path.name.startswith(".")]
        directories = [path for path in entries if path.is_dir() and path.name.lower() not in EXCLUDED_PARTS]
        if visible_files or len(directories) != 1:
            break
        current = directories[0]
    return current


def _prefix_evidence(evidence: list[dict], prefix: str) -> list[dict]:
    rows = []
    for item in evidence:
        row = dict(item)
        if row.get("file") and prefix:
            row["file"] = f"{prefix}/{row['file']}"
        if row.get("line_start") is None:
            row["document_locator"] = row.get("construct") or row.get("validation_backend")
        rows.append(row)
    return rows


def _native_entrypoint(backend: str, payloads: list[bytes]) -> str:
    text = "\n".join(payload.decode("utf-8", "replace") for payload in payloads)
    if backend == "cmake_ctest_native":
        for payload in reversed(payloads):
            try:
                tests = json.loads(payload.decode("utf-8", "replace")).get("tests", [])
                if tests:
                    return f"CTest target {tests[0].get('name', '<unnamed>')}"
            except (json.JSONDecodeError, AttributeError):
                pass
    if backend == "meson_native_introspection":
        for payload in reversed(payloads):
            try:
                tests = json.loads(payload.decode("utf-8", "replace"))
                if tests:
                    return f"Meson test {tests[0].get('name', '<unnamed>')}"
            except (json.JSONDecodeError, AttributeError):
                pass
    patterns = {
        "go_native_test_listing": r"(?m)^(Test|Example|Benchmark)\w+",
        "make_native_database": r"(?m)^(?:test|check)(?:-[^:]*)?\s*:",
        "pytest_native_collection": r"(?m)^\S+::\S+",
    }
    if backend in patterns and (match := re.search(patterns[backend], text)):
        return match.group(0).strip().rstrip(":")
    if backend == "node_package_script_metadata" and text.strip():
        return f"package.json test script: {text.strip().splitlines()[0][:180]}"
    if backend == "cargo_native_test_build":
        for line in text.splitlines():
            if '"test":true' in line:
                try:
                    row = json.loads(line)
                    return f"Cargo test target {row.get('target', {}).get('name', '<unnamed>')}"
                except json.JSONDecodeError:
                    break
    return backend


def _native_path(record: dict, root: Path, prefix: str, output_prefix: str) -> tuple[dict, dict[str, bytes]]:
    result, outputs = validate_native(record, root)
    evidence = []
    grouped: dict[str, list[bytes]] = {}
    for name, payload in outputs.items():
        backend = name.split(f"{record['case_id']}-", 1)[-1].rsplit("-", 1)[0]
        grouped.setdefault(backend, []).append(payload)
    for item in result["evidence"]:
        row = dict(item)
        old = Path(row.pop("native_output")).name
        payload = outputs[old]
        row.update({
            "file": f"{output_prefix}/{old}",
            "line_start": 1,
            "line_end": max(1, payload.count(b"\n")),
            "construct": "bounded offline native test discovery",
        })
        evidence.append(row)
    positive_backends = [
        row["backend"] for row in result["coverage"]
        if row["resolved"] and row["test_count"] > 0
    ]
    entrypoints = [_native_entrypoint(backend, grouped.get(backend, [])) for backend in positive_backends]
    positive = result["reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED"
    # Pytest collection is validator-injected; without a structured runner
    # configuration it cannot by itself turn test filenames into an entrypoint.
    return {
        "path": "A_NATIVE",
        "positive": positive,
        "state": result["reference_state"],
        "status": result["validation_status"],
        "families": result["family"],
        "entrypoints": entrypoints,
        "evidence": evidence,
        "limitations": result["limitations"],
        "source_root_prefix": prefix,
    }, outputs


def _structured_path(record: dict, root: Path, prefix: str) -> dict:
    result = validate_structured(record, root)
    return {
        "path": "B_STRUCTURED",
        "positive": result["reference_state"] == "U_TEST_ENTRYPOINT_RESOLVED",
        "state": result["reference_state"],
        "status": result["validation_status"],
        "families": result["family"],
        "entrypoints": [row["construct"] for row in result["evidence"]],
        "evidence": _prefix_evidence(result["evidence"], prefix),
        "limitations": result["limitations"],
        "source_root_prefix": prefix,
    }


def validate_observation(record: dict, repository_root: Path, output_prefix: str) -> tuple[dict, dict[str, bytes]]:
    if not record.get("source_tree"):
        return {
            "case_id": record["case_id"],
            "canonical_upstream": record["canonical_upstream"],
            "distribution": record["distribution"],
            "source_sha256": None,
            "family": [],
            "positive_path_count": 0,
            "resolved_entrypoint": None,
            "evidence": [],
            "path_results": [],
            "limitations": [f"Source content unavailable under the frozen acquisition record: {record.get('source_unavailable_reason', 'UNSPECIFIED')}"],
        }, {}
    source = repository_root / record["source_tree"]
    observed = tree_certificate(source)
    if observed != record["source_tree_certificate"]:
        raise RuntimeError(f"SOURCE_HASH_DRIFT:{record['case_id']}")
    resolved_root = project_root(source)
    prefix = resolved_root.relative_to(source).as_posix()
    if prefix == ".":
        prefix = ""
    local = dict(record)
    local["source_tree"] = resolved_root.relative_to(repository_root).as_posix()
    native, outputs = _native_path(local, repository_root, prefix, output_prefix)
    structured = _structured_path(local, repository_root, prefix)

    # Enforce the existing Python construct: native collection is insufficient
    # unless structured configuration independently establishes a runner surface.
    if native["positive"] and native["families"] == ["pytest_native_collection"]:
        python_structured = structured["positive"] and "python" in structured["families"]
        if not python_structured:
            native.update({
                "positive": False,
                "state": "VALIDATION_INDETERMINATE",
                "status": "NATIVE_COLLECTION_WITHOUT_SUPPORTED_CONFIGURATION",
                "entrypoints": [],
            })
            native["limitations"].append("Test collection without supported runner configuration does not satisfy the frozen U construct.")

    paths = [native, structured]
    positive_paths = [path for path in paths if path["positive"]]
    evidence = [item for path in positive_paths for item in path["evidence"]]
    entrypoints = sorted({item for path in positive_paths for item in path["entrypoints"] if item})
    families = sorted({item for path in paths for item in path["families"]})
    return {
        "case_id": record["case_id"],
        "canonical_upstream": record["canonical_upstream"],
        "distribution": record["distribution"],
        "source_sha256": observed["sha256"],
        "family": families,
        "positive_path_count": len(positive_paths),
        "resolved_entrypoint": "; ".join(entrypoints) if entrypoints else None,
        "evidence": evidence,
        "path_results": paths,
        "limitations": sorted({item for path in paths for item in path["limitations"]}),
    }, outputs


def positive_certificate(record: dict, repository_root: Path, output_prefix: str) -> tuple[dict, dict[str, bytes]]:
    base, outputs = validate_observation(record, repository_root, output_prefix)
    if base["positive_path_count"]:
        status = "ORTHOGONAL_POSITIVE_CERTIFIED"
        decision = "POSITIVE_CLAIM_CONFIRMED"
    else:
        status = "CERTIFICATION_INDETERMINATE"
        decision = "VALIDATION_INDETERMINATE"
    return {
        **base,
        "production_state_under_validation": "U_TEST_ENTRYPOINT_RESOLVED",
        "validator_backend": "state_specific_native_plus_structured_v1.0",
        "certificate_status": status,
        "decision": decision,
    }, outputs


def counterexample_search(record: dict, repository_root: Path, output_prefix: str) -> tuple[dict, dict[str, bytes]]:
    base, outputs = validate_observation(record, repository_root, output_prefix)
    if base["positive_path_count"] >= 2:
        status = "INDEPENDENT_COUNTEREXAMPLE_CONFIRMED"
        evidence_class = "TWO_PATH_AGREEMENT"
    elif base["positive_path_count"] == 1:
        path = next(path for path in base["path_results"] if path["positive"])
        status = "INDEPENDENT_COUNTEREXAMPLE_CONFIRMED"
        evidence_class = "NATIVE_SEMANTIC" if path["path"] == "A_NATIVE" else "STRUCTURED_SEMANTIC"
    else:
        status = "NO_CLEAR_COUNTEREXAMPLE_FOUND"
        evidence_class = None
    return {
        **base,
        "search_target": "SUPPORTED_ENTRYPOINT_MISSED_BY_PRODUCTION",
        "counterexample_status": status,
        "candidate_confidence": evidence_class,
        "interpretation": "No clear counterexample is not evidence that test capability is absent." if not base["positive_path_count"] else "A supported-domain executable entrypoint was independently recovered.",
    }, outputs
