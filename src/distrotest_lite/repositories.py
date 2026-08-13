from __future__ import annotations

import bz2
import gzip
import hashlib
import io
import json
import lzma
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import cmp_to_key
from pathlib import Path
from urllib.parse import urljoin, urlparse

import zstandard
from debian.deb822 import Sources
from debian.debian_support import Version as DebianVersion
from rpm_vercmp import vercmp as rpm_vercmp

from .common import config, ensure_layout, now_utc, sha256_bytes, write_json
from .http_cache import AcquisitionError, blob_path, fetch


def _decompress(data: bytes, name: str) -> bytes:
    if name.endswith(".xz"):
        return lzma.decompress(data)
    if name.endswith(".gz"):
        return gzip.decompress(data)
    if name.endswith(".bz2"):
        return bz2.decompress(data)
    if name.endswith(".zst"):
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
            return reader.read()
    return data


def _release_index(text: str) -> dict[str, tuple[str, int]]:
    block = text.split("SHA256:", 1)[1].split("SHA512:", 1)[0]
    result = {}
    for digest, size, path in re.findall(r"^\s+([0-9a-f]{64})\s+(\d+)\s+(\S+)\s*$", block, re.M):
        result[path] = (digest, int(size))
    return result


def acquire_deb_sources(distro: str) -> list[dict]:
    cfg = config()["repositories"][distro]
    rows: list[dict] = []
    reasons: list[dict] = []
    for suite in cfg["suites"]:
        base = cfg["base_urls"][suite]
        release_meta = fetch(f"{base}/dists/{suite}/InRelease")
        index = _release_index(blob_path(release_meta).read_text(errors="replace"))
        for component in cfg["components"]:
            candidates = [f"{component}/source/Sources.{ext}" for ext in ("xz", "gz", "bz2")]
            selected = next((path for path in candidates if path in index), None)
            if not selected:
                reasons.append({"suite": suite, "component": component, "reason": "SOURCE_INDEX_NOT_LISTED"})
                continue
            expected_sha, expected_size = index[selected]
            url = f"{base}/dists/{suite}/{selected}"
            meta = fetch(url)
            raw = blob_path(meta).read_bytes()
            if sha256_bytes(raw) != expected_sha or len(raw) != expected_size:
                raise RuntimeError(f"REPOSITORY_CHECKSUM_MISMATCH:{url}")
            text = _decompress(raw, selected).decode("utf-8", "replace")
            for para in Sources.iter_paragraphs(io.StringIO(text)):
                files = []
                for entry in para.get("Checksums-Sha256", []):
                    files.append({"sha256": entry["sha256"], "size": int(entry["size"]), "name": entry["name"]})
                rows.append({
                    "distribution": distro,
                    "suite": suite,
                    "component": component,
                    "source": str(para.get("Package", "")),
                    "version": str(para.get("Version", "")),
                    "homepage": str(para.get("Homepage", "")),
                    "vcs_git": str(para.get("Vcs-Git", "")),
                    "vcs_browser": str(para.get("Vcs-Browser", "")),
                    "directory": str(para.get("Directory", "")),
                    "files": files,
                    "source_index_sha256": meta["sha256"],
                    "source_index_url": url,
                })
    # Highest Debian version across normal stable repositories.
    chosen: dict[str, dict] = {}
    for row in rows:
        old = chosen.get(row["source"])
        if old is None or DebianVersion(row["version"]) > DebianVersion(old["version"]):
            chosen[row["source"]] = row
    root = ensure_layout()
    payload = {"distribution": distro, "created_at": now_utc(), "records": sorted(chosen.values(), key=lambda x: x["source"]), "index_reasons": reasons}
    write_json(root / "normalized" / f"{distro}_sources.json", payload)
    return payload["records"]


def _repomd_primary(repomd: bytes) -> tuple[str, str, int]:
    root = ET.fromstring(repomd)
    ns = {"r": "http://linux.duke.edu/metadata/repo"}
    for item in root.findall("r:data", ns):
        if item.attrib.get("type") == "primary":
            loc = item.find("r:location", ns)
            checksum = item.find("r:checksum", ns)
            size = item.find("r:size", ns)
            assert loc is not None and checksum is not None and size is not None
            return loc.attrib["href"], checksum.text or "", int(size.text or 0)
    raise RuntimeError("FEDORA_PRIMARY_NOT_LISTED")


def _rpm_compare(a: dict, b: dict) -> int:
    ae, be = int(a.get("epoch") or 0), int(b.get("epoch") or 0)
    if ae != be:
        return (ae > be) - (ae < be)
    value = rpm_vercmp(a["version"], b["version"])
    return value if value else rpm_vercmp(a["release"], b["release"])


def acquire_fedora_sources() -> list[dict]:
    rows: list[dict] = []
    repos = config()["repositories"]["fedora"]["repositories"]
    for repo, base in repos.items():
        repomd_meta = fetch(f"{base}/repodata/repomd.xml")
        href, expected_sha, expected_size = _repomd_primary(blob_path(repomd_meta).read_bytes())
        url = f"{base}/{href}"
        meta = fetch(url)
        raw = blob_path(meta).read_bytes()
        if sha256_bytes(raw) != expected_sha or len(raw) != expected_size:
            raise RuntimeError(f"REPOSITORY_CHECKSUM_MISMATCH:{url}")
        xml = _decompress(raw, href)
        ns = {"c": "http://linux.duke.edu/metadata/common", "r": "http://linux.duke.edu/metadata/rpm"}
        for _, elem in ET.iterparse(io.BytesIO(xml), events=("end",)):
            if elem.tag != "{http://linux.duke.edu/metadata/common}package":
                continue
            arch = elem.findtext("c:arch", namespaces=ns)
            if arch != "src":
                elem.clear()
                continue
            ver = elem.find("c:version", ns)
            loc = elem.find("c:location", ns)
            checksum = elem.find("c:checksum", ns)
            name = elem.findtext("c:name", namespaces=ns) or ""
            assert ver is not None and loc is not None and checksum is not None
            version, release, epoch = ver.attrib["ver"], ver.attrib["rel"], ver.attrib.get("epoch", "0")
            rows.append({
                "distribution": "fedora", "repository": repo, "source": name,
                "version": version, "release": release, "epoch": epoch,
                "nvr": f"{name}-{version}-{release}",
                "homepage": elem.findtext("c:url", namespaces=ns) or "",
                "summary": elem.findtext("c:summary", namespaces=ns) or "",
                "location": loc.attrib["href"], "rpm_sha256": checksum.text or "",
                "repository_base": base, "primary_sha256": meta["sha256"], "primary_url": url,
            })
            elem.clear()
    chosen: dict[str, dict] = {}
    for row in rows:
        old = chosen.get(row["source"])
        if old is None or _rpm_compare(row, old) > 0:
            chosen[row["source"]] = row
    payload = {"distribution": "fedora", "created_at": now_utc(), "records": sorted(chosen.values(), key=lambda x: x["source"])}
    write_json(ensure_layout() / "normalized" / "fedora_sources.json", payload)
    return payload["records"]


KNOWN_FORGES = {"github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "git.sr.ht"}


def canonical_url(value: str) -> tuple[str | None, str]:
    value = value.strip().split()[0] if value.strip() else ""
    value = re.sub(r"^git\+", "", value)
    if not value:
        return None, "NO_CANONICAL_UPSTREAM"
    try:
        parsed = urlparse(value if "://" in value else "https://" + value)
    except ValueError:
        return None, "NO_CANONICAL_UPSTREAM"
    host = parsed.hostname.lower().removeprefix("www.") if parsed.hostname else ""
    path = re.sub(r"/+", "/", parsed.path).strip("/")
    path = re.sub(r"\.git$", "", path, flags=re.I)
    if not host or not path:
        return None, "NO_CANONICAL_UPSTREAM"
    if host in KNOWN_FORGES:
        parts = path.split("/")
        # GitLab project paths can contain arbitrarily nested groups.  The
        # reserved `/-/` suffix introduces repository views such as tree/blob;
        # everything before it is the canonical project path.  Other supported
        # forges use fixed owner/project (or SourceHut owner) identities.
        if host == "gitlab.com":
            if "-" in parts:
                parts = parts[:parts.index("-")]
            if len(parts) < 2:
                return None, "NO_CANONICAL_UPSTREAM"
            path = "/".join(parts)
            return f"{host}/{path.lower()}", "EXACT_CANONICAL_FORGE_URL"
        # SourceHut repository identities are ~owner/project.  Owner-only
        # truncation collapses distinct repositories belonging to one account.
        needed = 2
        if len(parts) < needed:
            return None, "NO_CANONICAL_UPSTREAM"
        path = "/".join(parts[:needed])
        return f"{host}/{path.lower()}", "EXACT_CANONICAL_FORGE_URL"
    return f"{host}/{path.rstrip('/').lower()}", "EXACT_NORMALIZED_HOMEPAGE_URL"


def upstream_version(distribution: str, row: dict) -> str | None:
    raw = row["version"]
    if distribution in {"debian", "ubuntu"}:
        raw = raw.split(":", 1)[-1]
        if "-" in raw:
            raw = raw.rsplit("-", 1)[0]
    raw = raw.lower().removeprefix("v")
    raw = re.split(r"(?:\+dfsg\d*|\+ds\d*|\.dfsg\d*|~dfsg\d*|~ds\d*)", raw)[0]
    raw = raw.replace("_", ".")
    raw = re.sub(r"(?<=\d)[-+](?:release|stable)$", "", raw)
    return raw or None


def build_frame() -> dict:
    root = ensure_layout()
    debian = acquire_deb_sources("debian")
    fedora = acquire_fedora_sources()
    by_d: dict[str, list[dict]] = defaultdict(list)
    by_f: dict[str, list[dict]] = defaultdict(list)
    unresolved = []
    for distro, records, target in (("debian", debian, by_d), ("fedora", fedora, by_f)):
        for row in records:
            cid, method = canonical_url(row.get("homepage", ""))
            if cid:
                target[cid].append(row)
            else:
                unresolved.append({"distribution": distro, "source": row["source"], "reason": method})
    keys = sorted(set(by_d) & set(by_f))
    projects = []
    observations = []
    for cid in keys:
        ds, fs = by_d[cid], by_f[cid]
        ambiguous = len(ds) != 1 or len(fs) != 1
        reason = "LINEAGE_AMBIGUOUS" if ambiguous else None
        d_versions = sorted({upstream_version("debian", x) for x in ds})
        f_versions = sorted({upstream_version("fedora", x) for x in fs})
        same = not ambiguous and d_versions == f_versions and len(d_versions) == 1 and d_versions[0] is not None
        projects.append({
            "canonical_upstream": cid, "debian_lineages": [x["source"] for x in ds],
            "fedora_lineages": [x["source"] for x in fs], "lineage_state": "RESOLVED" if not ambiguous else "AMBIGUOUS",
            "reason": reason, "debian_upstream_versions": d_versions, "fedora_upstream_versions": f_versions,
            "c2v_candidate": same,
        })
        for distro, items in (("debian", ds), ("fedora", fs)):
            for item in items:
                observations.append({"canonical_upstream": cid, "distribution": distro, "upstream_version": upstream_version(distro, item), **item})
    payload = {
        "created_at": now_utc(), "method_version": config()["selection"]["lineage_version"],
        "project_count": len(projects), "observation_count": len(observations),
        "c2v_candidate_project_count": sum(x["c2v_candidate"] for x in projects),
        "projects": projects, "observations": observations,
        "unresolved_summary": {"NO_CANONICAL_UPSTREAM": len(unresolved)},
    }
    write_json(root / "derived" / "pre_outcome_frame.json", payload)
    frame_hash = hashlib.sha256((root / "derived" / "pre_outcome_frame.json").read_bytes()).hexdigest()
    write_json(root / "manifests" / "pre_outcome_frame_freeze.json", {
        "frozen_at": now_utc(), "path": "derived/pre_outcome_frame.json", "sha256": frame_hash,
        "project_count": len(projects), "observation_count": len(observations),
        "c2v_candidate_project_count": payload["c2v_candidate_project_count"],
    })
    return payload


def select_pilot() -> dict:
    root = ensure_layout()
    frame_path = root / "derived" / "pre_outcome_frame.json"
    frame = json.loads(frame_path.read_text())
    namespace = config()["phase0"]["namespace"]
    eligible = [p for p in frame["projects"] if p["lineage_state"] == "RESOLVED"]
    ranked = sorted(eligible, key=lambda p: (hashlib.sha256((namespace + "\0" + p["canonical_upstream"]).encode()).hexdigest(), p["canonical_upstream"]))
    selected = []
    obs_lookup = defaultdict(list)
    for obs in frame["observations"]:
        obs_lookup[obs["canonical_upstream"]].append(obs)
    for rank, project in enumerate(ranked[: config()["phase0"]["pilot_projects"]], 1):
        selected.append({"rank": rank, "selection_hash": hashlib.sha256((namespace + "\0" + project["canonical_upstream"]).encode()).hexdigest(), **project, "observations": sorted(obs_lookup[project["canonical_upstream"]], key=lambda x: x["distribution"])})
    manifest = {
        "namespace": namespace, "selection_method": "ascending SHA-256(namespace + NUL + canonical_upstream)",
        "input_frame_sha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(), "eligible_project_count": len(eligible),
        "selected_project_count": len(selected), "projects": selected,
    }
    path = root / "manifests" / "pilot_40.json"
    write_json(path, manifest)
    write_json(root / "manifests" / "pilot_40_freeze.json", {"path": "manifests/pilot_40.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "namespace": namespace})
    return manifest
