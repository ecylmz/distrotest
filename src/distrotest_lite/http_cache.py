from __future__ import annotations

import json
import random
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .common import ensure_layout, now_utc, sha256_bytes, write_json


class AcquisitionError(RuntimeError):
    def __init__(self, reason: str, url: str, detail: str):
        super().__init__(f"{reason}: {url}: {detail}")
        self.reason = reason
        self.url = url
        self.detail = detail


def fetch(url: str, *, timeout: float = 90, attempts: int = 5, refresh: bool = False) -> dict:
    root = ensure_layout()
    key = sha256_bytes(url.encode())
    index = root / "raw" / "url-index" / f"{key}.json"
    if index.exists() and not refresh:
        meta = json.loads(index.read_text())
        blob = root / meta["blob"]
        if blob.exists() and sha256_bytes(blob.read_bytes()) == meta["sha256"]:
            return meta

    headers = {"User-Agent": "DistroTest-Lite-Phase0/0.1 (+scientific-research)"}
    last = ""
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(url)
                if response.status_code == 404:
                    raise AcquisitionError("HTTP_NOT_FOUND", url, "404")
                response.raise_for_status()
                data = response.content
                digest = sha256_bytes(data)
                rel = Path("raw") / "by-sha256" / digest[:2] / digest
                blob = root / rel
                blob.parent.mkdir(parents=True, exist_ok=True)
                if not blob.exists():
                    blob.write_bytes(data)
                meta = {
                    "url": url,
                    "final_url": str(response.url),
                    "retrieved_at": now_utc(),
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "content_encoding": response.headers.get("content-encoding"),
                    "etag": response.headers.get("etag"),
                    "last_modified": response.headers.get("last-modified"),
                    "size": len(data),
                    "sha256": digest,
                    "blob": str(rel),
                }
                write_json(index, meta)
                return meta
            except AcquisitionError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                last = f"{type(exc).__name__}: {exc}"
                if attempt < attempts:
                    time.sleep(min(16.0, 0.75 * 2 ** (attempt - 1)) + random.Random(key + str(attempt)).random() / 4)
    raise AcquisitionError("NETWORK_RETRIES_EXHAUSTED", url, last)


def blob_path(meta: dict) -> Path:
    return ensure_layout() / meta["blob"]
