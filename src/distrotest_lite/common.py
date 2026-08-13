from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "phase0.json"


def config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def namespace_root() -> Path:
    return ROOT / "data" / "work" / "repository_indices"


def ensure_layout() -> Path:
    root = namespace_root()
    for rel in (
        "raw/by-sha256", "raw/url-index", "normalized", "derived", "manifests",
        "fixtures/u", "fixtures/p", "fixtures/l", "audit", "logs"
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(data))


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
