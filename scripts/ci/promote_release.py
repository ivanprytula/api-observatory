#!/usr/bin/env python3
"""Promote a published release into the application image lock."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from promote_mvp_images import promote, validate_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote release metadata into image lock"
    )
    parser.add_argument(
        "--metadata-base64", type=str, help="Base64-encoded release metadata"
    )
    parser.add_argument(
        "--metadata-file", type=Path, help="Path to release metadata JSON"
    )
    parser.add_argument(
        "--lock", type=Path, default=Path("environments/aws-dev/images.lock.json")
    )
    args = parser.parse_args(argv)

    raw = args.metadata_base64 or os.environ.get("RELEASE_METADATA", "")
    if args.metadata_file:
        raw = args.metadata_file.read_text(encoding="utf-8")
    elif not raw:
        print("RELEASE_METADATA is required", file=sys.stderr)
        return 1

    try:
        decoded = base64.b64decode(raw).decode("utf-8") if args.metadata_base64 else raw
    except Exception as exc:
        print(f"Failed to decode release metadata: {exc}", file=sys.stderr)
        return 1

    metadata = json.loads(decoded)
    errors = validate_metadata(metadata)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1

    promote(metadata, args.lock)
    print(f"Promoted {args.lock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
