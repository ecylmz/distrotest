#!/usr/bin/env python3
"""Collect normalized source-package indices from official repositories."""

from __future__ import annotations

import argparse
import json

from distrotest_lite.common import ensure_layout
from distrotest_lite.repositories import acquire_deb_sources, acquire_fedora_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution", choices=["debian", "fedora", "ubuntu", "all"])
    args = parser.parse_args()
    selected = ("debian", "fedora", "ubuntu") if args.distribution == "all" else (args.distribution,)
    counts = {}
    for distribution in selected:
        rows = acquire_fedora_sources() if distribution == "fedora" else acquire_deb_sources(distribution)
        counts[distribution] = len(rows)
    print(json.dumps({"output": str(ensure_layout() / "normalized"), "records": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
