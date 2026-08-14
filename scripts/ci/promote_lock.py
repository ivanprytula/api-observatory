#!/usr/bin/env python3
"""Merge release metadata into the application image lock."""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "environments/aws-dev/images.lock.json"


def _load_metadata(raw: str) -> dict[str, object]:
    decoded = base64.b64decode(raw).decode("utf-8") if "{" not in raw else raw
    return json.loads(decoded)


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(data, temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, mode)
    os.replace(temporary_path, path)


def promote(metadata: dict[str, object], lock_path: Path = DEFAULT_LOCK) -> None:
    current = json.loads(lock_path.read_text(encoding="utf-8"))
    merged = dict(current)
    merged["schema_version"] = 1
    merged["source_commit_sha"] = metadata["source_commit_sha"]
    merged["source_tree_sha"] = metadata["source_tree_sha"]
    merged["contracts_version"] = metadata["contracts_version"]
    merged["images"] = metadata.get("images", {})
    _atomic_write(lock_path, merged)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-base64", type=str)
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()

    raw = args.metadata_base64 or os.environ.get("RELEASE_METADATA", "")
    if args.metadata_file:
        raw = args.metadata_file.read_text(encoding="utf-8")
    if not raw:
        print(
            "RELEASE_METADATA or --metadata-file is required", __import__("sys").stderr
        )
        return 1

    metadata = _load_metadata(raw)
    promote(metadata, args.lock)
    print(f"Promoted {args.lock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
