from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import html
import io
import json
import lzma
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tarfile
import time
import xmlrpc.client
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin

import httpx

from .classifiers import classify_l_text, classify_p, classify_u
from .common import ROOT, canonical_json, sha256_file
from .pilot_acquire import _normalize_log, _safe_name
from .repositories import canonical_url, upstream_version


CONFIG_PATH = ROOT / "config" / "full_study.json"
FROOT = ROOT / "data" / "work"
PHASE0_ROOT = ROOT / "data" / "manifests" / "source_indices"


def cfg() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def now_utc() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(data))


def ensure_layout() -> Path:
    for rel in ("raw/by-sha256", "raw/url-index", "normalized/sources", "normalized/logs", "derived", "manifests", "audit", "tables", "logs"):
        (FROOT / rel).mkdir(parents=True, exist_ok=True)
    return FROOT


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def verify_prerequisites() -> dict:
    c = cfg()
    checks = {
        "spec_sha256": sha256_file(ROOT / c["protocol"]["path"]),
        "phase0_report_sha256": sha256_file(ROOT / c["phase0_report"]["path"]),
        "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
        "frame_sha256": sha256_file(ROOT / c["frame"]["path"]),
    }
    for name, expected in (
        ("spec_sha256", c["protocol"]["sha256"]),
        ("phase0_report_sha256", c["phase0_report"]["sha256"]),
        ("frame_sha256", c["frame"]["sha256"]),
    ):
        if checks[name] != expected:
            raise RuntimeError(f"{name.upper()}_MISMATCH:{checks[name]}:{expected}")
    frame = json.loads((ROOT / c["frame"]["path"]).read_text())
    resolved = [p for p in frame["projects"] if p["lineage_state"] == "RESOLVED"]
    counts = {
        "unambiguous_projects": len(resolved),
        "c2v_projects": sum(p["c2v_candidate"] for p in resolved),
        "non_c2v_projects": sum(not p["c2v_candidate"] for p in resolved),
    }
    for key, value in counts.items():
        if value != c["frame"][key]:
            raise RuntimeError(f"FRAME_COUNT_MISMATCH:{key}:{value}:{c['frame'][key]}")
    test = subprocess.run(["uv", "run", "pytest", "-q", "-o", "addopts="], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    passed = __import__("re").search(r"(\d+) passed", test.stdout)
    if test.returncode or not passed or int(passed.group(1)) < 38:
        raise RuntimeError(f"PHASE0_FIXTURE_FAILURE:{test.stdout.strip()}")
    result = {
        "verified_at": now_utc(), **checks, **counts,
        "fixture_status": f"{passed.group(1)}/{passed.group(1)} PASS", "fixture_output": test.stdout.strip(),
        "python": sys.version, "os": platform.platform(), "git_commit": _git("rev-parse", "HEAD"),
        "git_status_porcelain": (_git("status", "--porcelain") or "").splitlines(),
        "rules": c["rules"], "ontology_version": c["rules"]["ontology"],
    }
    write_json(ensure_layout() / "manifests" / "prerequisite_freeze.json", result)
    return result


def freeze_sample() -> dict:
    verify_prerequisites()
    c = cfg()
    frame_path = ROOT / c["frame"]["path"]
    frame = json.loads(frame_path.read_text())
    namespace = c["sample"]["namespace"]
    observations: dict[str, list[dict]] = defaultdict(list)
    for row in frame["observations"]:
        observations[row["canonical_upstream"]].append(row)
    population = [p for p in frame["projects"] if p["lineage_state"] == "RESOLVED"]
    strata = {"C2V": [p for p in population if p["c2v_candidate"]], "NON_C2V": [p for p in population if not p["c2v_candidate"]]}

    def digest(cid: str) -> str:
        return hashlib.sha256((namespace + "\0" + cid).encode()).hexdigest()

    population_rows = []
    for p in sorted(population, key=lambda x: x["canonical_upstream"]):
        population_rows.append({
            "canonical_upstream": p["canonical_upstream"],
            "stratum": "C2V" if p["c2v_candidate"] else "NON_C2V",
            "selection_hash": digest(p["canonical_upstream"]),
            "debian_lineage": p["debian_lineages"][0], "fedora_lineage": p["fedora_lineages"][0],
            "debian_upstream_version": p["debian_upstream_versions"][0],
            "fedora_upstream_version": p["fedora_upstream_versions"][0],
        })
    population_manifest = {
        "namespace": namespace, "input_frame_sha256": sha256_file(frame_path),
        "selection_method": c["sample"]["method"], "project_count": len(population_rows), "projects": population_rows,
    }
    pop_path = ensure_layout() / "manifests" / "population_manifest.json"
    write_json(pop_path, population_manifest)

    selections = []
    stratum_outputs = {}
    for stratum, conf_key in (("C2V", "c2v"), ("NON_C2V", "non_c2v")):
        spec = c["sample"][conf_key]
        ranked = sorted(strata[stratum], key=lambda p: (digest(p["canonical_upstream"]), p["canonical_upstream"]))
        if len(ranked) != spec["population"]:
            raise RuntimeError(f"STRATUM_POPULATION_MISMATCH:{stratum}:{len(ranked)}:{spec['population']}")
        pi = spec["sample"] / spec["population"]
        weight = 1.0 / pi
        rows = []
        for rank, p in enumerate(ranked[:spec["sample"]], 1):
            row = {
                "stratum": stratum, "stratum_rank": rank, "selection_hash": digest(p["canonical_upstream"]),
                "inclusion_probability_fraction": f"{spec['sample']}/{spec['population']}",
                "inclusion_probability": pi, "design_weight": weight, **p,
                "observations": sorted(observations[p["canonical_upstream"]], key=lambda x: x["distribution"]),
            }
            rows.append(row); selections.append(row)
        manifest = {
            "namespace": namespace, "stratum": stratum, "population": spec["population"], "sample": spec["sample"],
            "inclusion_probability_fraction": f"{spec['sample']}/{spec['population']}",
            "inclusion_probability": pi, "design_weight": weight, "projects": rows,
        }
        path = ensure_layout() / "manifests" / ("s1_c2v_manifest.json" if stratum == "C2V" else "s0_non_c2v_manifest.json")
        write_json(path, manifest)
        stratum_outputs[stratum] = {"path": str(path.relative_to(FROOT)), "sha256": sha256_file(path), **{k: manifest[k] for k in ("population", "sample", "inclusion_probability_fraction", "inclusion_probability", "design_weight")}}
    for sample_id, row in enumerate(sorted(selections, key=lambda x: (x["stratum"], x["stratum_rank"])), 1):
        row["sample_id"] = sample_id
    final = {
        "frozen_at": now_utc(), "namespace": namespace, "selection_method": c["sample"]["method"],
        "input_frame_sha256": sha256_file(frame_path), "population_manifest_sha256": sha256_file(pop_path),
        "selected_project_count": len(selections), "strata": stratum_outputs,
        "projects": sorted(selections, key=lambda x: x["sample_id"]),
    }
    final_path = ensure_layout() / "manifests" / "sample_200.json"
    write_json(final_path, final)
    freeze = {
        "path": str(final_path.relative_to(FROOT)), "sha256": sha256_file(final_path),
        "population_manifest": {"path": str(pop_path.relative_to(FROOT)), "sha256": sha256_file(pop_path)},
        "strata": stratum_outputs, "namespace": namespace, "selected_project_count": len(selections),
    }
    write_json(ensure_layout() / "manifests" / "sample_freeze.json", freeze)
    return freeze


class AcquisitionError(RuntimeError):
    pass


def _fetch(url: str, *, attempts: int = 5, timeout: float = 90) -> dict:
    root = ensure_layout()
    key = hashlib.sha256(url.encode()).hexdigest()
    index = root / "raw" / "url-index" / f"{key}.json"
    if index.exists():
        meta = json.loads(index.read_text())
        blob = root / meta["blob"]
        if blob.exists() and sha256_file(blob) == meta["sha256"]:
            return meta
    last = ""
    headers = {"User-Agent": "DistroTest-Lite-FullStudy/1.1 (+scientific-research)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(url)
                if response.status_code == 404:
                    raise AcquisitionError(f"HTTP_NOT_FOUND:{url}")
                response.raise_for_status()
                data = response.content
                digest = hashlib.sha256(data).hexdigest()
                rel = Path("raw") / "by-sha256" / digest[:2] / digest
                blob = root / rel
                blob.parent.mkdir(parents=True, exist_ok=True)
                if not blob.exists(): blob.write_bytes(data)
                meta = {"url": url, "final_url": str(response.url), "retrieved_at": now_utc(), "status": response.status_code,
                        "content_type": response.headers.get("content-type"), "size": len(data), "sha256": digest, "blob": str(rel)}
                write_json(index, meta)
                return meta
            except AcquisitionError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                last = f"{type(exc).__name__}: {exc}"
                if attempt < attempts:
                    time.sleep(min(16, .75 * 2 ** (attempt - 1)) + random.Random(key + str(attempt)).random() / 4)
    raise AcquisitionError(f"NETWORK_RETRIES_EXHAUSTED:{url}:{last}")


def _blob(meta: dict) -> Path:
    return ensure_layout() / meta["blob"]


def _materialize(meta: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists(): return
    try: os.link(_blob(meta), destination)
    except OSError: shutil.copyfile(_blob(meta), destination)


def _sample() -> dict:
    return json.loads((ROOT / "data" / "manifests" / "sample_revision.json").read_text())


def rpm_primary_source_name(srpm: Path) -> str:
    """Return RPM's Source0 basename from immutable SRPM header metadata."""
    query = subprocess.run(
        ["rpm", "-qp", "--qf", "%{SOURCE}", str(srpm)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    name = query.stdout.strip()
    if query.returncode or not name or name == "(none)" or Path(name).name != name:
        raise RuntimeError(f"PRIMARY_SOURCE_METADATA_UNRESOLVED:{query.stderr.strip()}")
    return name


def source_archive_candidates(extracted: Path, primary_name: str) -> list[dict]:
    """Describe archive-like SRPM payloads and their source role."""
    rows = []
    for path in sorted(extracted.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            kind = "rubygem" if path.suffix.lower() == ".gem" else "zip" if zipfile.is_zipfile(path) else "tar" if tarfile.is_tarfile(path) else None
        except OSError:
            kind = None
        if kind:
            rows.append({
                "name": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "archive_kind": kind,
                "role": "PRIMARY_SOURCE0" if path.name == primary_name else "AUXILIARY_SOURCE",
            })
    return rows


def primary_source_extraction_kind(archive: Path) -> str:
    if archive.suffix.lower() == ".gem":
        return "RUBYGEM_DATA_TAR"
    if zipfile.is_zipfile(archive):
        return "ZIP"
    if tarfile.is_tarfile(archive):
        return "TAR"
    raise RuntimeError(f"PRIMARY_SOURCE_NOT_SUPPORTED_ARCHIVE:{archive.name}")


def extract_primary_source_archive(archive: Path, destination: Path) -> str:
    """Extract a Source0 tar, zip, or RubyGem payload deterministically."""
    destination.mkdir(parents=True, exist_ok=True)
    kind = primary_source_extraction_kind(archive)
    if kind == "RUBYGEM_DATA_TAR":
        with tarfile.open(archive) as outer:
            data_member = next((member for member in outer.getmembers() if Path(member.name).name == "data.tar.gz" and member.isfile()), None)
            if data_member is None:
                raise RuntimeError("RUBYGEM_DATA_ARCHIVE_UNAVAILABLE")
            stream = outer.extractfile(data_member)
            if stream is None:
                raise RuntimeError("RUBYGEM_DATA_ARCHIVE_UNREADABLE")
            with tarfile.open(fileobj=io.BytesIO(stream.read()), mode="r:gz") as payload:
                payload.extractall(destination, filter="data")
        return kind
    if kind == "ZIP":
        with zipfile.ZipFile(archive) as payload:
            payload.extractall(destination)
        return kind
    if kind == "TAR":
        with tarfile.open(archive) as payload:
            payload.extractall(destination, filter="data")
        return kind
    raise AssertionError(f"unsupported extraction kind: {kind}")


def _source_one(project: dict, obs: dict) -> dict:
    cid, distro, source = project["canonical_upstream"], obs["distribution"], obs["source"]
    target = ensure_layout() / "normalized" / "sources" / distro / _safe_name(cid)
    target.mkdir(parents=True, exist_ok=True)
    record = {"canonical_upstream": cid, "distribution": distro, "source": source, "version": obs.get("version"),
              "nvr": obs.get("nvr"), "repository_origin": obs.get("suite") or obs.get("repository"),
              "upstream_version": obs.get("upstream_version"), "state": "UNAVAILABLE", "reason": None, "files": []}
    try:
        if distro == "debian":
            base = obs["source_index_url"].split("/dists/", 1)[0] + "/"
            for item in obs["files"]:
                url = urljoin(base, f"{obs['directory']}/{item['name']}")
                meta = _fetch(url)
                if meta["sha256"] != item["sha256"] or meta["size"] != item["size"]: raise RuntimeError("SOURCE_FILE_IDENTITY_MISMATCH")
                dest = target / item["name"]; _materialize(meta, dest)
                record["files"].append({"name": item["name"], "url": url, "sha256": meta["sha256"], "size": meta["size"]})
            dsc = next(target.glob("*.dsc"), None)
            if dsc is None: raise RuntimeError("DSC_UNAVAILABLE")
            tree = target / "tree"
            if not tree.exists():
                subprocess.run(["dpkg-source", "-x", str(dsc), str(tree)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            record.update(state="AVAILABLE", tree=str(tree.relative_to(FROOT)))
        else:
            url = f"{obs['repository_base']}/{obs['location']}"
            meta = _fetch(url)
            if meta["sha256"] != obs["rpm_sha256"]: raise RuntimeError("SOURCE_RPM_IDENTITY_MISMATCH")
            srpm = target / Path(obs["location"]).name; _materialize(meta, srpm)
            extracted = target / "srpm"; extracted.mkdir(exist_ok=True)
            marker = extracted / ".extracted"
            if not marker.exists():
                p1 = subprocess.Popen(["rpm2cpio", str(srpm)], stdout=subprocess.PIPE)
                p2 = subprocess.run(["cpio", "-idm", "--quiet"], cwd=extracted, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                assert p1.stdout is not None; p1.stdout.close()
                if p1.wait() or p2.returncode: raise RuntimeError("SOURCE_RPM_EXTRACTION_FAILED")
                marker.write_text("ok\n")
            primary_name = rpm_primary_source_name(srpm)
            candidates = source_archive_candidates(extracted, primary_name)
            primary = extracted / primary_name
            if not primary.exists():
                raise RuntimeError(f"PRIMARY_SOURCE_PAYLOAD_UNAVAILABLE:{primary_name}")
            source_tree = extracted / "upstream-primary-v2"; source_tree.mkdir(exist_ok=True)
            extraction_kind = primary_source_extraction_kind(primary)
            if not any(source_tree.iterdir()):
                extract_primary_source_archive(primary, source_tree)
            record["files"].append({"name": srpm.name, "url": url, "sha256": meta["sha256"], "size": meta["size"]})
            record.update(
                state="AVAILABLE",
                tree=str(source_tree.relative_to(FROOT)),
                packaging_tree=str(extracted.relative_to(FROOT)),
                primary_source={"name": primary_name, "sha256": sha256_file(primary), "archive_kind": extraction_kind},
                source_artifacts=candidates,
            )
    except Exception as exc:
        record.update(state="UNAVAILABLE", reason="UPSTREAM_SOURCE_UNAVAILABLE" if distro == "debian" else "PACKAGE_SOURCE_UNAVAILABLE", detail=f"{type(exc).__name__}: {exc}")
    return record


def acquire_sources(workers: int = 8) -> dict:
    sample = _sample(); tasks = [(p, o) for p in sample["projects"] for o in p["observations"]]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_source_one, p, o): (p["canonical_upstream"], o["distribution"]) for p, o in tasks}
        for future in concurrent.futures.as_completed(future_map):
            records.append(future.result())
            if len(records) % 10 == 0: write_json(ensure_layout() / "derived" / "source_acquisition.partial.json", {"updated_at": now_utc(), "records": records})
    records.sort(key=lambda x: (x["canonical_upstream"], x["distribution"]))
    payload = {"completed_at": now_utc(), "records": records}
    write_json(ensure_layout() / "derived" / "source_acquisition.json", payload)
    return payload


def _debian_log(obs: dict, cid: str) -> dict:
    pkg, version, arch = obs["source"], obs["version"], "amd64"
    page_url = f"https://buildd.debian.org/status/logs.php?pkg={quote(pkg)}&ver={quote(version)}&arch={arch}"
    page = _fetch(page_url); page_text = _blob(page).read_text(errors="replace")
    links = [html.unescape(x) for x in re.findall(r'href="([^\"]*fetch\.php\?[^\"]+)"', page_text)]
    links = [x for x in links if f"pkg={quote(pkg)}" in x or f"pkg={pkg}" in x]
    base = {"canonical_upstream": cid, "distribution": "debian", "source": pkg, "version": version,
            "repository_origin": obs.get("suite"), "upstream_version": obs.get("upstream_version"), "architecture": arch,
            "index_url": page_url, "index_sha256": page["sha256"]}
    if not links: return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "BUILD_LOG_UNAVAILABLE"}
    log_url = re.sub(r"raw=0", "raw=1", urljoin("https://buildd.debian.org/status/", links[0]))
    meta = _fetch(log_url); text = _normalize_log(_blob(meta).read_bytes())
    identity = {"package": bool(re.search(rf"(?:Source:|Building source package)\s*{re.escape(pkg)}\b|{re.escape(pkg)}_{re.escape(version)}", text, re.I)),
                "version": version in text, "architecture": bool(re.search(r"(?:Build Architecture|Architecture):\s*amd64\b|buildd.*amd64", text, re.I))}
    path = ensure_layout() / "normalized" / "logs" / "debian" / f"{_safe_name(cid)}.log"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    warnings = (["BUILD_LOG_TRUNCATED"] if re.search(r"log (?:was )?truncated|output truncated", text, re.I) else []) + ([] if all(identity.values()) else ["LOG_IDENTITY_CHECK_FAILED"])
    success = bool(re.search(r"Build finished at|dpkg-buildpackage: info: full upload", text, re.I))
    return {**base, "state": "AVAILABLE" if all(identity.values()) and not "BUILD_LOG_TRUNCATED" in warnings else "L_LOG_INCOMPLETE_OR_UNPARSABLE",
            "reason": warnings[0] if warnings else None, "official_identifier": log_url, "url": log_url, "retrieved_at": meta["retrieved_at"],
            "raw_sha256": meta["sha256"], "raw_size": meta["size"], "raw_blob": meta["blob"], "normalized_path": str(path.relative_to(FROOT)),
            "normalized_log_sha256": sha256_file(path), "identity": identity, "warnings": warnings, "build_status": "SUCCESS" if success else "STATUS_UNRESOLVED"}


def _koji_call(method: str, *args):
    last = None
    for attempt in range(5):
        try: return getattr(xmlrpc.client.ServerProxy("https://koji.fedoraproject.org/kojihub", allow_none=True), method)(*args)
        except Exception as exc:
            last = exc
            if attempt < 4: time.sleep(2 ** attempt)
    raise RuntimeError(f"KOJI_API_RETRIES_EXHAUSTED:{method}:{last}")


def _fedora_log(obs: dict, cid: str) -> dict:
    nvr = obs["nvr"]
    build = _koji_call("getBuild", nvr)
    base = {"canonical_upstream": cid, "distribution": "fedora", "source": obs["source"], "version": obs["version"], "nvr": nvr,
            "repository_origin": obs.get("repository"), "upstream_version": obs.get("upstream_version"), "architecture": "x86_64"}
    if not build or build.get("nvr") != nvr: return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "OFFICIAL_BUILD_ID_UNRESOLVED"}
    descendants = _koji_call("getTaskDescendents", build["task_id"], {})
    tasks = [t for children in descendants.values() for t in children if t.get("method") == "buildArch" and t.get("arch") == "x86_64"]
    if not tasks: return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "X86_64_BUILD_TASK_UNRESOLVED", "build_id": build["build_id"], "build_task_id": build["task_id"]}
    task = sorted(tasks, key=lambda t: t["id"])[0]
    info = _koji_call("getTaskInfo", task["id"], {"request": True}); output_arch = info.get("request", [None, None, "x86_64"])[2]
    url = f"https://kojipkgs.fedoraproject.org/packages/{quote(build['name'])}/{quote(build['version'])}/{quote(build['release'])}/data/logs/{quote(output_arch)}/build.log"
    details = {"build_id": build["build_id"], "build_task_id": build["task_id"], "task_id": task["id"], "task_worker_architecture": task["arch"], "output_architecture": output_arch, "url": url}
    try: meta = _fetch(url)
    except Exception as exc: return {**base, **details, "state": "L_LOG_UNAVAILABLE", "reason": "BUILD_LOG_UNAVAILABLE", "detail": f"{type(exc).__name__}: {exc}"}
    text = _normalize_log(_blob(meta).read_bytes())
    identity = {"package": bool(re.search(rf"\b{re.escape(build['name'])}\b", text, re.I)), "version": build["version"] in text and build["release"] in text,
                "architecture": task["arch"] == "x86_64" and output_arch in {"x86_64", "noarch"}}
    path = ensure_layout() / "normalized" / "logs" / "fedora" / f"{_safe_name(cid)}.log"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    warnings = (["BUILD_LOG_TRUNCATED"] if re.search(r"log (?:was )?truncated|output truncated", text, re.I) else []) + ([] if all(identity.values()) else ["LOG_IDENTITY_CHECK_FAILED"])
    return {**base, **details, "state": "AVAILABLE" if all(identity.values()) and not "BUILD_LOG_TRUNCATED" in warnings else "L_LOG_INCOMPLETE_OR_UNPARSABLE",
            "reason": warnings[0] if warnings else None, "official_identifier": f"koji-build:{build['build_id']}/task:{task['id']}/build.log", "retrieved_at": meta["retrieved_at"],
            "raw_sha256": meta["sha256"], "raw_size": meta["size"], "raw_blob": meta["blob"], "normalized_path": str(path.relative_to(FROOT)),
            "normalized_log_sha256": sha256_file(path), "identity": identity, "warnings": warnings, "build_status": "SUCCESS" if build.get("state") == 1 else str(build.get("state"))}


def _log_one(project: dict, obs: dict) -> dict:
    try: return _debian_log(obs, project["canonical_upstream"]) if obs["distribution"] == "debian" else _fedora_log(obs, project["canonical_upstream"])
    except Exception as exc:
        return {"canonical_upstream": project["canonical_upstream"], "distribution": obs["distribution"], "source": obs["source"],
                "version": obs.get("version"), "nvr": obs.get("nvr"), "state": "L_LOG_UNAVAILABLE", "reason": "ACQUISITION_ERROR", "detail": f"{type(exc).__name__}: {exc}"}


def acquire_logs(workers: int = 12) -> dict:
    sample = _sample(); tasks = [(p, o) for p in sample["projects"] for o in p["observations"]]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_log_one, p, o) for p, o in tasks]
        for future in concurrent.futures.as_completed(futures):
            records.append(future.result())
            if len(records) % 20 == 0: write_json(ensure_layout() / "derived" / "log_acquisition.partial.json", {"updated_at": now_utc(), "records": records})
    records.sort(key=lambda x: (x["canonical_upstream"], x["distribution"]))
    payload = {"completed_at": now_utc(), "records": records}
    write_json(ensure_layout() / "derived" / "log_acquisition.json", payload)
    return payload


def classify() -> dict:
    c = cfg(); sample = _sample()
    sources = json.loads((ensure_layout() / "derived" / "source_acquisition.json").read_text())["records"]
    logs = json.loads((ensure_layout() / "derived" / "log_acquisition.json").read_text())["records"]
    smap = {(x["canonical_upstream"], x["distribution"]): x for x in sources}
    u, p, l = [], [], []
    for project in sample["projects"]:
        cid = project["canonical_upstream"]
        for distro in ("debian", "fedora"):
            rec = smap.get((cid, distro))
            if not rec or rec["state"] != "AVAILABLE":
                ur = {"state": "U_UNRESOLVED", "family": None, "rules": [], "reason": "UPSTREAM_SOURCE_UNAVAILABLE"}
                pr = {"labels": ["P_UNRESOLVED"], "reason": "PACKAGING_RECIPE_UNAVAILABLE", "evidence": []}
            else:
                ur = classify_u(ensure_layout() / rec["tree"])
                pr = classify_p(distro, ensure_layout() / rec["tree"], ensure_layout() / rec.get("packaging_tree", rec["tree"]))
            u.append({"canonical_upstream": cid, "distribution": distro, **ur})
            p.append({"canonical_upstream": cid, "distribution": distro, **pr})
    for log in logs:
        if log["state"] == "AVAILABLE": lr = classify_l_text((ensure_layout() / log["normalized_path"]).read_text(errors="replace"))
        else: lr = {"state": log["state"], "evidence": [], "zero_evidence": []}
        l.append({"canonical_upstream": log["canonical_upstream"], "distribution": log["distribution"], "source_log_sha256": log.get("raw_sha256"),
                  "source_log": log.get("official_identifier"), **lr})
    payload = {"classified_at": now_utc(), "rule_versions": c["rules"], "u": u, "p": p, "l": l}
    path = ensure_layout() / "derived" / "automatic_upl_labels.json"; write_json(path, payload)
    freeze = {"path": str(path.relative_to(FROOT)), "sha256": sha256_file(path), "frozen_at": now_utc(), "rule_versions": c["rules"]}
    write_json(ensure_layout() / "manifests" / "automatic_labels_freeze.json", freeze)
    return freeze


def c2a() -> dict:
    sample = _sample(); sources = json.loads((ensure_layout() / "derived" / "source_acquisition.json").read_text())["records"]
    smap = {(x["canonical_upstream"], x["distribution"]): x for x in sources}; rows = []
    for p in sample["projects"]:
        if p["stratum"] != "C2V": continue
        d, f = smap[(p["canonical_upstream"], "debian")], smap[(p["canonical_upstream"], "fedora")]
        primary_debian = [
            x for x in d.get("files", [])
            if re.search(r"\.orig\.tar\.", x["name"])
            and not re.search(r"\.orig-[^.]+\.tar\.", x["name"])
            and not x["name"].endswith(".asc")
        ]
        dh = {x["sha256"] for x in primary_debian}
        fh = set(); fedora_primary = f.get("primary_source")
        packaging = ensure_layout() / f.get("packaging_tree", "missing")
        if fedora_primary:
            fh.add(fedora_primary["sha256"])
        elif packaging.exists():
            srpms = sorted(packaging.parent.glob("*.src.rpm"))
            if srpms:
                primary_name = rpm_primary_source_name(srpms[0])
                primary_path = packaging / primary_name
                if primary_path.exists(): fh.add(sha256_file(primary_path))
        state = "C2A_EXACT" if dh & fh else ("C2A_ARTIFACT_DIFFERS" if dh and fh else "C2A_UNRESOLVED")
        rows.append({
            "canonical_upstream": p["canonical_upstream"],
            "state": state,
            "identity_role": "PRIMARY_UPSTREAM_ARCHIVE",
            "debian_primary_upstream_artifacts": primary_debian,
            "fedora_primary_upstream_artifact": fedora_primary,
            "debian_upstream_artifact_sha256": sorted(dh),
            "fedora_upstream_artifact_sha256": sorted(fh),
        })
    payload = {"classified_at": now_utc(), "identity_rule": "byte-identical primary upstream archive SHA-256 (Debian primary orig archive versus Fedora RPM Source0)", "rows": rows}
    write_json(ensure_layout() / "derived" / "c2a.json", payload); return payload


def ubuntu_secondary(workers: int = 6) -> dict:
    # Reuse the Phase 0 frozen Ubuntu source index; do not refresh or widen repository policy.
    source_file = PHASE0_ROOT / "ubuntu_sources.json"
    if not source_file.exists():
        payload = {"completed_at": now_utc(), "state": "NOT_ESTIMABLE", "reason": "FROZEN_UBUNTU_METADATA_UNAVAILABLE", "records": []}
        write_json(ensure_layout() / "derived" / "ubuntu_secondary.json", payload); return payload
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for row in json.loads(source_file.read_text())["records"]:
        cid, _ = canonical_url(row.get("homepage", ""))
        if cid: by_cid[cid].append(row)
    pocket = {"resolute": "Release", "resolute-updates": "Updates", "resolute-security": "Security"}

    def one(project: dict) -> dict:
        cid = project["canonical_upstream"]; candidates = by_cid.get(cid, [])
        if len(candidates) != 1: return {"canonical_upstream": cid, "state": "L_LOG_UNAVAILABLE", "reason": "NO_CANONICAL_UPSTREAM" if not candidates else "LINEAGE_AMBIGUOUS"}
        obs = candidates[0]; pock = pocket[obs["suite"]]
        params = urlencode({"ws.op": "getBuildRecords", "source_name": obs["source"], "pocket": pock, "ws.size": 75})
        api_url = f"https://api.launchpad.net/1.0/ubuntu/resolute?{params}"
        base = {"canonical_upstream": cid, "source": obs["source"], "version": obs["version"], "upstream_version": upstream_version("ubuntu", obs),
                "suite": obs["suite"], "pocket": pock, "architecture": "amd64", "api_url": api_url}
        try:
            api = _fetch(api_url); data = json.loads(_blob(api).read_text())
            builds = [x for x in data.get("entries", []) if x.get("source_package_version") == obs["version"] and x.get("arch_tag") == "amd64"]
            if len(builds) != 1 or not builds[0].get("build_log_url"):
                return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "OFFICIAL_BUILD_ID_UNRESOLVED" if not builds else "BUILD_LOG_UNAVAILABLE", "api_sha256": api["sha256"]}
            build = builds[0]; meta = _fetch(build["build_log_url"]); raw = _blob(meta).read_bytes()
            try: decoded = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            except gzip.BadGzipFile: decoded = raw
            text = _normalize_log(decoded)
            identity = {"package": bool(re.search(rf"(?:Source:|Building source package)\s*{re.escape(obs['source'])}\b|{re.escape(obs['source'])}_", text, re.I)),
                        "version": obs["version"] in text, "architecture": bool(re.search(r"(?:Build Architecture|Architecture):\s*amd64\b|ubuntu-resolute-amd64", text, re.I))}
            path = ensure_layout() / "normalized" / "logs" / "ubuntu" / f"{_safe_name(cid)}.log"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
            lr = classify_l_text(text) if all(identity.values()) else {"state": "L_LOG_INCOMPLETE_OR_UNPARSABLE", "evidence": [], "zero_evidence": []}
            return {**base, "state": lr["state"], "reason": None if all(identity.values()) else "LOG_IDENTITY_CHECK_FAILED", "build_id": build["self_link"].rsplit("/", 1)[-1],
                    "official_identifier": build["self_link"], "url": build["build_log_url"], "raw_sha256": meta["sha256"], "normalized_path": str(path.relative_to(FROOT)), "identity": identity, "l_evidence": lr["evidence"]}
        except Exception as exc: return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "ACQUISITION_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool: records = list(pool.map(one, _sample()["projects"]))
    records.sort(key=lambda x: x["canonical_upstream"])
    available = sum(x["state"] not in {"L_LOG_UNAVAILABLE", "L_LOG_INCOMPLETE_OR_UNPARSABLE"} for x in records)
    payload = {"completed_at": now_utc(), "state": "USABLE" if available else "NOT_ESTIMABLE", "available_logs": available, "records": records}
    write_json(ensure_layout() / "derived" / "ubuntu_secondary.json", payload); return payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="distrotest-lite-full")
    parser.add_argument("command", choices=["sources", "logs", "classify", "c2a", "ubuntu"])
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    result = {
        "sources": lambda: acquire_sources(args.workers or 8),
        "logs": lambda: acquire_logs(args.workers or 12),
        "classify": classify,
        "c2a": c2a,
        "ubuntu": lambda: ubuntu_secondary(args.workers or 6),
    }[args.command]()
    print(json.dumps(result if args.command == "classify" else {"command": args.command, "records": len(result.get("records", [])), "state": result.get("state")}, sort_keys=True))


if __name__ == "__main__":
    main()
