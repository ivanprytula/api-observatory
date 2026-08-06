"""Validate the portable application image release manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / "release/services.json"
ROOT = MANIFEST.parent.parent
EXPECTED_SERVICES = {
    "ingestor": (8000, "/health", "/readyz"),
    "inference": (8001, "/health", "/readyz"),
    "dashboard": (8501, "/_stcore/health", "/_stcore/health"),
}


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if manifest.get("image_tag_template") != "tree-{full_tree_sha}":
        errors.append("image_tag_template must preserve full tree identity")
    services = manifest.get("services", [])
    names = [item.get("name") for item in services]
    if set(names) != set(EXPECTED_SERVICES) or len(names) != len(set(names)):
        errors.append("services must be ingestor, inference, and dashboard")
    for service in services:
        for key in (
            "dockerfile",
            "build_context",
            "port",
            "health_path",
            "readiness_path",
        ):
            if not service.get(key):
                errors.append(f"{service.get('name', 'unknown')}: missing {key}")
        name = service.get("name")
        if name not in EXPECTED_SERVICES:
            continue
        port, health_path, readiness_path = EXPECTED_SERVICES[name]
        if (
            service.get("port"),
            service.get("health_path"),
            service.get("readiness_path"),
        ) != (port, health_path, readiness_path):
            errors.append(
                f"{name}: port or health contract does not match the MVP workload"
            )
        dockerfile = ROOT / str(service.get("dockerfile", ""))
        build_context = ROOT / str(service.get("build_context", ""))
        if not dockerfile.is_file():
            errors.append(f"{name}: dockerfile does not exist")
        if not build_context.is_dir():
            errors.append(f"{name}: build context does not exist")
    non_deployable = manifest.get("non_deployable_services", [])
    if [item.get("name") for item in non_deployable] != ["mcp"]:
        errors.append("mcp must remain the only explicitly non-deployable service")
    if errors:
        print(*errors, sep="\n", file=sys.stderr)
        return 1
    print("Release manifest is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
