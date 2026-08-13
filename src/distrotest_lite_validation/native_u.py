"""Validator A: bounded, offline native build/test discovery."""

from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import subprocess
from pathlib import Path


MAX_OUTPUT = 1_000_000


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_native_output(value: bytes) -> bytes:
    """Remove non-semantic runtime jitter while retaining diagnostic content."""
    text = value.decode("utf-8", "replace")
    text = re.sub(r"\b\d+\.\d+s\b", "<ELAPSED>", text)
    text = re.sub(r"(?m)^(# Make data base, printed on ).*$", r"\1<TIMESTAMP>", text)
    text = re.sub(r"(?m)^(# Finished Make data base on ).*$", r"\1<TIMESTAMP>", text)
    lines = text.splitlines()
    downloads = sorted(line for line in lines if line.startswith("go: downloading "))
    other = [line for line in lines if not line.startswith("go: downloading ")]
    normalized = "\n".join(downloads + other)
    if text.endswith("\n"):
        normalized += "\n"
    return normalized.encode("utf-8")


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NPROC, (4096, 4096))


def _sandbox_prefix(source: Path) -> list[str]:
    command = ["bwrap", "--unshare-net", "--die-with-parent"]
    for host in ("/usr", "/usr/local", "/bin", "/lib", "/lib64", "/etc"):
        if Path(host).exists():
            command.extend(["--ro-bind", host, host])
    venv = Path(__file__).resolve().parents[2] / ".venv"
    if venv.exists():
        command.extend(["--ro-bind", str(venv), "/venv"])
    command.extend([
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind", str(source.resolve()), "/src", "--chdir", "/src",
        "--setenv", "HOME", "/tmp", "--setenv", "XDG_CACHE_HOME", "/tmp/cache",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "PATH", "/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "--setenv", "http_proxy", "", "--setenv", "https_proxy", "",
        "--setenv", "HTTP_PROXY", "", "--setenv", "HTTPS_PROXY", "",
        "--setenv", "ALL_PROXY", "", "--setenv", "NO_PROXY", "*",
        "--setenv", "GOPROXY", "off", "--setenv", "GOSUMDB", "off",
        "--setenv", "GOCACHE", "/tmp/go-cache", "--setenv", "CARGO_NET_OFFLINE", "true",
        "--setenv", "CARGO_TARGET_DIR", "/tmp/cargo-target",
    ])
    return command


def _run(source: Path, argv: list[str], timeout_seconds: int = 25) -> dict:
    rendered = " ".join(argv)
    try:
        proc = subprocess.run(
            _sandbox_prefix(source) + argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
            preexec_fn=_limits,
        )
        output = _normalize_native_output(proc.stdout[:MAX_OUTPUT])
        rendered_output = output.decode("utf-8", "replace")
        return {
            "command": rendered,
            "exit_code": proc.returncode,
            "timed_out": False,
            "output_sha256": _sha256_bytes(rendered_output.encode("utf-8")),
            "output": rendered_output,
            "output_truncated": len(proc.stdout) > MAX_OUTPUT,
        }
    except subprocess.TimeoutExpired as error:
        output = _normalize_native_output((error.stdout or b"")[:MAX_OUTPUT])
        rendered_output = output.decode("utf-8", "replace")
        return {
            "command": rendered,
            "exit_code": None,
            "timed_out": True,
            "output_sha256": _sha256_bytes(rendered_output.encode("utf-8")),
            "output": rendered_output,
            "output_truncated": False,
        }


def _asset_files(source: Path) -> list[str]:
    result = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(source)
        if {part.lower() for part in relative_path.parts} & {"debian", ".pc", ".git", "vendor", "node_modules", "target", ".tox", ".venv"}:
            continue
        relative = relative_path.as_posix()
        parts = {part.lower() for part in relative_path.parts}
        name = path.name.lower()
        if parts & {"test", "tests", "t", "spec", "specs", "testing"} or name.endswith(("_test.go", "_test.py", "test.py", ".t")) or name.startswith("test_"):
            result.append(relative)
    return result[:200]


def _cmake(source: Path) -> dict:
    first = _run(source, ["cmake", "-S", "/src", "-B", "/tmp/cmake-build", "-DBUILD_TESTING=ON", "-Wno-dev"])
    runs = [first]
    if first["exit_code"] == 0:
        runs.append(_run(source, ["ctest", "--test-dir", "/tmp/cmake-build", "--show-only=json-v1"]))
    success = len(runs) == 2 and runs[-1]["exit_code"] == 0
    count = 0
    if success:
        try:
            count = len(json.loads(runs[-1]["output"]).get("tests", []))
        except json.JSONDecodeError:
            success = False
    return {"backend": "cmake_ctest_native", "runs": runs, "resolved": success, "test_count": count}


def _meson(source: Path) -> dict:
    first = _run(source, ["meson", "setup", "/tmp/meson-build", "/src", "--wrap-mode=nodownload"])
    runs = [first]
    if first["exit_code"] == 0:
        runs.append(_run(source, ["meson", "introspect", "/tmp/meson-build", "--tests"]))
    success = len(runs) == 2 and runs[-1]["exit_code"] == 0
    count = 0
    if success:
        try:
            count = len(json.loads(runs[-1]["output"]))
        except json.JSONDecodeError:
            success = False
    return {"backend": "meson_native_introspection", "runs": runs, "resolved": success, "test_count": count}


def _go(source: Path) -> dict:
    run = _run(source, ["go", "test", "-list", ".", "./..."])
    names = [line for line in run["output"].splitlines() if re.match(r"^(Test|Example|Benchmark)\w+", line)]
    return {"backend": "go_native_test_listing", "runs": [run], "resolved": run["exit_code"] == 0, "test_count": len(names)}


def _cargo(source: Path) -> dict:
    run = _run(source, ["cargo", "test", "--no-run", "--offline", "--message-format=json"])
    count = sum(1 for line in run["output"].splitlines() if '"profile"' in line and '"test":true' in line and '"executable"' in line)
    return {"backend": "cargo_native_test_build", "runs": [run], "resolved": run["exit_code"] == 0, "test_count": count}


def _python(source: Path) -> dict:
    run = _run(source, ["/venv/bin/python", "-m", "pytest", "--collect-only", "-q", "-o", "cache_dir=/tmp/pytest-cache", "--ignore=debian", "--ignore=.pc", "--ignore=vendor"])
    match = re.search(r"(\d+) tests? collected", run["output"])
    if not match:
        match = re.search(r"collected (\d+) items?", run["output"])
    count = int(match.group(1)) if match else sum(1 for line in run["output"].splitlines() if "::test" in line.lower())
    return {"backend": "pytest_native_collection", "runs": [run], "resolved": run["exit_code"] in {0, 5}, "test_count": count}


def _make(source: Path) -> dict:
    run = _run(source, ["make", "-qp"])
    resolved = run["exit_code"] in {0, 1}
    count = len(re.findall(r"(?m)^(?:test|check)(?:-[^:]*)?\s*:(?![=])", run["output"])) if resolved else 0
    return {"backend": "make_native_database", "runs": [run], "resolved": resolved, "test_count": count}


def _node(source: Path) -> dict:
    program = "const p=require('/src/package.json'); const s=p.scripts&&p.scripts.test; if(s) console.log(s);"
    run = _run(source, ["node", "-e", program])
    text = run["output"].strip().lower()
    positive = bool(text) and "no test specified" not in text
    return {"backend": "node_package_script_metadata", "runs": [run], "resolved": run["exit_code"] == 0, "test_count": int(positive)}


def validate_case(record: dict, root: Path) -> tuple[dict, dict[str, bytes]]:
    source = root / record["source_tree"]
    backends = []
    if (source / "CMakeLists.txt").exists():
        backends.append(_cmake(source))
    if (source / "meson.build").exists():
        backends.append(_meson(source))
    if (source / "go.mod").exists():
        backends.append(_go(source))
    if (source / "Cargo.toml").exists():
        backends.append(_cargo(source))
    if any((source / name).exists() for name in ("pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini")):
        backends.append(_python(source))
    if any((source / name).exists() for name in ("Makefile.am", "Makefile.in", "configure.ac", "configure.in")):
        backends.append(_make(source))
    if (source / "package.json").exists():
        backends.append(_node(source))

    output_files: dict[str, bytes] = {}
    evidence = []
    for backend in backends:
        for index, run in enumerate(backend["runs"], start=1):
            name = f"{record['case_id']}-{backend['backend']}-{index}.txt"
            payload = run.pop("output").encode("utf-8")
            output_files[name] = payload
            evidence.append({
                "construct": "native test discovery",
                "validation_backend": backend["backend"],
                "native_command": run["command"],
                "native_output": f"data/validation/native_outputs/a/{name}",
                "native_output_sha256": run["output_sha256"],
                "exit_code": run["exit_code"],
                "timed_out": run["timed_out"],
                "output_truncated": run["output_truncated"],
            })
    positives = [backend for backend in backends if backend["resolved"] and backend["test_count"] > 0]
    unresolved = [backend for backend in backends if not backend["resolved"]]
    assets = _asset_files(source)
    if positives:
        state = "U_TEST_ENTRYPOINT_RESOLVED"
        status = "RESOLVED_POSITIVE_NATIVE"
        reason = "At least one bounded offline native backend discovered a nonzero test target or test collection."
        entrypoint = "; ".join(f"{item['backend']} ({item['test_count']})" for item in positives)
    elif not backends or unresolved:
        state = "VALIDATION_INDETERMINATE"
        status = "VALIDATION_INDETERMINATE"
        reason = "No native positive was found and at least one applicable backend was unavailable, failed, timed out, or no safe native backend applied."
        entrypoint = None
    elif assets:
        state = "U_TEST_ASSETS_ONLY"
        status = "RESOLVED_NATIVE_ZERO_WITH_ASSETS"
        reason = "All applicable native discovery paths completed without a test target, while test-like assets were present."
        entrypoint = None
    else:
        state = "U_NO_TEST_CAPABILITY_RESOLVED"
        status = "RESOLVED_NATIVE_ZERO_NO_ASSETS"
        reason = "All applicable native discovery paths completed without a test target and the bounded asset inventory was empty."
        entrypoint = None
    coverage = [{"backend": item["backend"], "resolved": item["resolved"], "test_count": item["test_count"]} for item in backends]
    certificate = {
        "case_id": record["case_id"],
        "source_sha256": record["source_tree_certificate"]["sha256"],
        "validation_backend": "validator_a_native_v1.1.1-contract-aligned",
        "validation_status": status,
        "reference_state": state,
        "family": [item["backend"] for item in backends],
        "evidence": evidence,
        "resolved_entrypoint": entrypoint,
        "reason": reason,
        "coverage": coverage,
        "absence_checklist_complete": bool(backends) and all(item["resolved"] for item in backends),
        "asset_examples": assets[:20],
        "limitations": ["Native configuration can be indeterminate when dependencies or tools are unavailable; indeterminate is never converted to a negative state."],
    }
    return certificate, output_files
