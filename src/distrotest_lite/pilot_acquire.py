from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import xmlrpc.client
from pathlib import Path
from urllib.parse import quote, urljoin

from .common import config, ensure_layout, now_utc, sha256_bytes, write_json
from .http_cache import AcquisitionError, blob_path, fetch


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _pilot() -> dict:
    return json.loads((ensure_layout() / "manifests" / "pilot_40.json").read_text())


def _materialize(meta: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = blob_path(meta)
    if not destination.exists():
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)


def acquire_pilot_sources() -> dict:
    root = ensure_layout()
    records = []
    for project in _pilot()["projects"]:
        cid = project["canonical_upstream"]
        for obs in project["observations"]:
            distro, source = obs["distribution"], obs["source"]
            target = root / "normalized" / "pilot_sources" / distro / _safe_name(cid)
            target.mkdir(parents=True, exist_ok=True)
            record = {"canonical_upstream": cid, "distribution": distro, "source": source, "state": "UNAVAILABLE", "reason": None, "files": []}
            try:
                if distro == "debian":
                    base = obs["source_index_url"].split("/dists/", 1)[0] + "/"
                    for item in obs["files"]:
                        url = urljoin(base, f'{obs["directory"]}/{item["name"]}')
                        meta = fetch(url)
                        if meta["sha256"] != item["sha256"] or meta["size"] != item["size"]:
                            raise RuntimeError("SOURCE_FILE_IDENTITY_MISMATCH")
                        destination = target / item["name"]
                        _materialize(meta, destination)
                        record["files"].append({"name": item["name"], "url": url, "sha256": meta["sha256"], "size": meta["size"]})
                    dsc = next(target.glob("*.dsc"), None)
                    if not dsc:
                        raise RuntimeError("DSC_UNAVAILABLE")
                    extracted = target / "tree"
                    if not extracted.exists():
                        subprocess.run(["dpkg-source", "-x", str(dsc), str(extracted)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    record.update(state="AVAILABLE", reason=None, tree=str(extracted.relative_to(root)))
                else:
                    url = f'{obs["repository_base"]}/{obs["location"]}'
                    meta = fetch(url)
                    if meta["sha256"] != obs["rpm_sha256"]:
                        raise RuntimeError("SOURCE_RPM_IDENTITY_MISMATCH")
                    srpm = target / Path(obs["location"]).name
                    _materialize(meta, srpm)
                    extracted = target / "srpm"
                    extracted.mkdir(exist_ok=True)
                    marker = extracted / ".extracted"
                    if not marker.exists():
                        p1 = subprocess.Popen(["rpm2cpio", str(srpm)], stdout=subprocess.PIPE)
                        p2 = subprocess.run(["cpio", "-idm", "--quiet"], cwd=extracted, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        assert p1.stdout is not None
                        p1.stdout.close()
                        if p1.wait() or p2.returncode:
                            raise RuntimeError("SOURCE_RPM_EXTRACTION_FAILED")
                        marker.write_text("ok\n")
                    source_tree = extracted / "upstream"
                    source_tree.mkdir(exist_ok=True)
                    archive = next((p for p in extracted.iterdir() if p.is_file() and tarfile.is_tarfile(p)), None)
                    if archive and not any(source_tree.iterdir()):
                        with tarfile.open(archive) as tf:
                            tf.extractall(source_tree, filter="data")
                    record["files"].append({"name": srpm.name, "url": url, "sha256": meta["sha256"], "size": meta["size"]})
                    record.update(state="AVAILABLE", reason=None, tree=str(source_tree.relative_to(root)), packaging_tree=str(extracted.relative_to(root)))
            except (AcquisitionError, OSError, subprocess.SubprocessError, RuntimeError, tarfile.TarError) as exc:
                record["reason"] = "UPSTREAM_SOURCE_UNAVAILABLE" if distro == "debian" else "PACKAGE_SOURCE_UNAVAILABLE"
                record["detail"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            write_json(root / "derived" / "pilot_source_acquisition.partial.json", {"updated_at": now_utc(), "records": records})
    payload = {"completed_at": now_utc(), "records": records}
    write_json(root / "derived" / "pilot_source_acquisition.json", payload)
    return payload


def _normalize_log(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _debian_log(obs: dict, cid: str) -> dict:
    pkg, version, arch = obs["source"], obs["version"], "amd64"
    page_url = f"https://buildd.debian.org/status/logs.php?pkg={quote(pkg)}&ver={quote(version)}&arch={arch}"
    page = fetch(page_url)
    page_text = blob_path(page).read_text(errors="replace")
    links = re.findall(r'href="([^\"]*fetch\.php\?[^\"]+)"', page_text)
    links = [html.unescape(x) for x in links if f"pkg={quote(pkg)}" in html.unescape(x) or f"pkg={pkg}" in html.unescape(x)]
    if not links:
        return {"canonical_upstream": cid, "distribution": "debian", "source": pkg, "version": version, "architecture": arch, "state": "L_LOG_UNAVAILABLE", "reason": "BUILD_LOG_UNAVAILABLE", "index_url": page_url, "index_sha256": page["sha256"]}
    log_url = urljoin("https://buildd.debian.org/status/", links[0])
    log_url = re.sub(r"raw=0", "raw=1", log_url)
    meta = fetch(log_url)
    text = _normalize_log(blob_path(meta).read_bytes())
    identity = {
        "package": bool(re.search(rf"(?:Source:|Building source package)\s*{re.escape(pkg)}\b|{re.escape(pkg)}_{re.escape(version)}", text, re.I)),
        "version": version in text,
        "architecture": bool(re.search(r"(?:Build Architecture|Architecture):\s*amd64\b|buildd.*amd64", text, re.I)),
    }
    normalized = ensure_layout() / "normalized" / "logs" / "debian" / f"{_safe_name(cid)}.log"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_text(text)
    warnings = []
    if re.search(r"log (?:was )?truncated|output truncated", text, re.I): warnings.append("BUILD_LOG_TRUNCATED")
    if not all(identity.values()): warnings.append("LOG_IDENTITY_CHECK_FAILED")
    return {"canonical_upstream": cid, "distribution": "debian", "source": pkg, "version": version, "architecture": arch,
            "state": "AVAILABLE" if all(identity.values()) else "L_LOG_INCOMPLETE_OR_UNPARSABLE", "reason": warnings[0] if warnings else None,
            "official_identifier": log_url, "url": log_url, "retrieved_at": meta["retrieved_at"], "raw_sha256": meta["sha256"], "raw_size": meta["size"],
            "raw_blob": meta["blob"], "normalized_path": str(normalized.relative_to(ensure_layout())), "identity": identity, "warnings": warnings}


def _koji_call(server, method: str, *args):
    last = None
    for attempt in range(5):
        try:
            return getattr(server, method)(*args)
        except Exception as exc:
            last = exc
            if attempt < 4: time.sleep(2 ** attempt)
    raise RuntimeError(f"KOJI_API_RETRIES_EXHAUSTED:{method}:{last}")


def _fedora_log(obs: dict, cid: str) -> dict:
    nvr = obs["nvr"]
    server = xmlrpc.client.ServerProxy("https://koji.fedoraproject.org/kojihub", allow_none=True)
    build = _koji_call(server, "getBuild", nvr)
    base = {"canonical_upstream": cid, "distribution": "fedora", "source": obs["source"], "nvr": nvr, "architecture": "x86_64"}
    if not build or build.get("nvr") != nvr:
        return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "OFFICIAL_BUILD_ID_UNRESOLVED"}
    descendants = _koji_call(server, "getTaskDescendents", build["task_id"], {})
    tasks = [t for children in descendants.values() for t in children if t.get("method") == "buildArch" and t.get("arch") == "x86_64"]
    if not tasks:
        return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "X86_64_BUILD_TASK_UNRESOLVED", "build_id": build["build_id"], "build_task_id": build["task_id"]}
    task = sorted(tasks, key=lambda t: t["id"])[0]
    info = _koji_call(server, "getTaskInfo", task["id"], {"request": True})
    output_arch = info.get("request", [None, None, "x86_64"])[2]
    url = f'https://kojipkgs.fedoraproject.org/packages/{quote(build["name"])}/{quote(build["version"])}/{quote(build["release"])}/data/logs/{quote(output_arch)}/build.log'
    try:
        meta = fetch(url)
    except AcquisitionError as exc:
        return {**base, "state": "L_LOG_UNAVAILABLE", "reason": "BUILD_LOG_UNAVAILABLE", "detail": str(exc), "build_id": build["build_id"], "build_task_id": build["task_id"], "task_id": task["id"], "task_worker_architecture": task["arch"], "output_architecture": output_arch, "url": url}
    text = _normalize_log(blob_path(meta).read_bytes())
    identity = {
        "package": bool(re.search(rf"\b{re.escape(build['name'])}\b", text, re.I)),
        "version": build["version"] in text and build["release"] in text,
        "architecture": task["arch"] == "x86_64" and output_arch in {"x86_64", "noarch"},
    }
    normalized = ensure_layout() / "normalized" / "logs" / "fedora" / f"{_safe_name(cid)}.log"
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_text(text)
    warnings = []
    if re.search(r"log (?:was )?truncated|output truncated", text, re.I): warnings.append("BUILD_LOG_TRUNCATED")
    if not all(identity.values()): warnings.append("LOG_IDENTITY_CHECK_FAILED")
    return {**base, "state": "AVAILABLE" if all(identity.values()) else "L_LOG_INCOMPLETE_OR_UNPARSABLE", "reason": warnings[0] if warnings else None,
            "build_id": build["build_id"], "build_task_id": build["task_id"], "task_id": task["id"], "task_worker_architecture": task["arch"], "output_architecture": output_arch,
            "official_identifier": f'koji-build:{build["build_id"]}/task:{task["id"]}/build.log', "url": url, "retrieved_at": meta["retrieved_at"],
            "raw_sha256": meta["sha256"], "raw_size": meta["size"], "raw_blob": meta["blob"], "normalized_path": str(normalized.relative_to(ensure_layout())), "identity": identity, "warnings": warnings}


def acquire_pilot_logs() -> dict:
    root = ensure_layout()
    records = []
    for project in _pilot()["projects"]:
        cid = project["canonical_upstream"]
        for obs in project["observations"]:
            try:
                record = _debian_log(obs, cid) if obs["distribution"] == "debian" else _fedora_log(obs, cid)
            except Exception as exc:
                record = {"canonical_upstream": cid, "distribution": obs["distribution"], "source": obs["source"], "state": "L_LOG_UNAVAILABLE", "reason": "ACQUISITION_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
            records.append(record)
            write_json(root / "derived" / "pilot_log_acquisition.partial.json", {"updated_at": now_utc(), "records": records})
    payload = {"completed_at": now_utc(), "records": records}
    write_json(root / "derived" / "pilot_log_acquisition.json", payload)
    return payload
