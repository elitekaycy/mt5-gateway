#!/usr/bin/env python3
"""Refuses a promotion unless both images are attested for exactly this source.

The fingerprint covers what can change a running gateway. Docs, tests, CI and release
notes are left out, so a version bump or docs change does not need a new broker run.

    attestation/verify.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import required_cases  # noqa: E402

VARIANTS = ("vnc", "headless")
FINGERPRINTED = (
    "Dockerfile",
    "Dockerfile.headless",
    "app/",
    "defaults/",
    "root/",
    "root-headless/",
    "scripts/",
)


def source_fingerprint(repo: Path) -> str:
    """Hashes every tracked runtime file's path and content, e.g. 'c0ffee…' (16 hex)."""
    listed = subprocess.run(
        ["git", "ls-files", "--", *FINGERPRINTED],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    digest = hashlib.sha256()
    for name in sorted(filter(None, listed)):
        digest.update(name.encode() + b"\0" + (repo / name).read_bytes() + b"\0")
    return digest.hexdigest()[:16]


def record_problems(
    record: dict[str, Any], fingerprint: str, variant: str
) -> list[str]:
    """Everything wrong with one record. An empty list means it attests this source."""
    problems = []
    if record.get("fingerprint") != fingerprint:
        problems.append(f"{variant}: record is for {record.get('fingerprint')}")
    if record.get("variant") != variant:
        problems.append(f"{variant}: record is for variant {record.get('variant')}")
    cases = record.get("cases", {})
    for name in required_cases(variant):
        if name not in cases:
            problems.append(f"{variant}: missing case {name}")
        elif cases[name].get("ok") is not True:
            problems.append(f"{variant}: failed case {name}")
    return problems


def problems_for(repo: Path) -> list[str]:
    fingerprint = source_fingerprint(repo)
    problems = []
    for variant in VARIANTS:
        path = repo / "attestation" / "records" / f"{fingerprint}-{variant}.json"
        if not path.exists():
            problems.append(
                f"{variant}: no attestation record for source {fingerprint}"
            )
            continue
        problems += record_problems(json.loads(path.read_text()), fingerprint, variant)
    return problems


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    problems = problems_for(repo)
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        print(
            "Run attestation/run.py --record on both images. See docs/contributing/attestation.md"
        )
        return 1
    print(f"attested: source {source_fingerprint(repo)} on {', '.join(VARIANTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
