"""Independent host-aware repository identity canonicalisation."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


FIXED_TWO = {"github.com", "codeberg.org", "bitbucket.org"}
VIEW_MARKERS = {"tree", "blob", "commit", "commits", "issues", "pull", "pulls", "releases"}


def independent_identity(raw: str) -> dict:
    value = (raw or "").strip().split()[0] if (raw or "").strip() else ""
    value = re.sub(r"^git\+", "", value, flags=re.I)
    if not value:
        return {"identity": None, "status": "UNRESOLVED_EMPTY", "reason": "empty URL"}
    if re.match(r"^[^/@\s]+@[^:/\s]+:", value):
        value = "ssh://" + value.replace(":", "/", 1)
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return {"identity": None, "status": "UNRESOLVED_PARSE", "reason": "URL parse failure"}
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[-1].lower().endswith(".git"):
        segments[-1] = segments[-1][:-4]
    if not host or not segments or any(segment in {".", ".."} for segment in segments):
        return {"identity": None, "status": "UNRESOLVED_SHAPE", "reason": "missing or unsafe host/path"}

    normalized_view = False
    if host == "gitlab.com":
        if "-" in segments:
            index = segments.index("-")
            normalized_view = True
            segments = segments[:index]
        if len(segments) < 2:
            return {"identity": None, "status": "UNRESOLVED_SHAPE", "reason": "GitLab needs namespace/project"}
        project = segments
    elif host == "git.sr.ht":
        if len(segments) < 2 or not segments[0].startswith("~"):
            return {"identity": None, "status": "UNRESOLVED_SHAPE", "reason": "SourceHut needs ~owner/project"}
        project = segments[:2]
        normalized_view = len(segments) > 2
    elif host in FIXED_TWO:
        if len(segments) < 2:
            return {"identity": None, "status": "UNRESOLVED_SHAPE", "reason": "forge needs owner/project"}
        project = segments[:2]
        normalized_view = len(segments) > 2 and segments[2].lower() in VIEW_MARKERS
    else:
        project = segments
    identity = f"{host}/{'/'.join(project)}".lower().rstrip("/")
    return {
        "identity": identity,
        "status": "RESOLVED",
        "reason": "host-specific path grammar",
        "host": host,
        "view_suffix_normalized": normalized_view,
    }
