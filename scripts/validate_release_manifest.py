"""Validate the portable application image release manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / "release/services.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if manifest.get("image_tag_template") != "tree-{full_tree_sha}":
        errors.append("image_tag_template must preserve full tree identity")
    names = {item.get("name") for item in manifest.get("services", [])}
    if names != {"ingestor", "inference", "dashboard"}:
        errors.append("services must be ingestor, inference, and dashboard")
    for service in manifest.get("services", []):
        for key in (
            "dockerfile",
            "build_context",
            "port",
            "health_path",
            "readiness_path",
        ):
            if not service.get(key):
                errors.append(f"{service.get('name', 'unknown')}: missing {key}")
    if errors:
        print(*errors, sep="\n", file=sys.stderr)
        return 1
    print("Release manifest is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
