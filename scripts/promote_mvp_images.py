"""Promote published application release metadata into the AWS MVP lock."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "environments/aws-dev/images.lock.json"
EXPECTED_REPOSITORY = "ivanprytula/api-observatory"
EXPECTED_SERVICES = {"ingestor", "inference", "dashboard"}
SUPPORTED_PROFILES = {"inference", "cache", "broker", "monitoring"}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_SHA = "0" * 40
PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def validate_metadata(metadata: dict[str, Any]) -> list[str]:
    """Return validation errors for published application release metadata."""
    errors: list[str] = []
    if metadata.get("schema_version") != 1:
        errors.append("release metadata schema_version must be 1")
    if metadata.get("source_repository") != EXPECTED_REPOSITORY:
        errors.append(f"source_repository must be {EXPECTED_REPOSITORY}")
    for field in ("source_commit_sha", "source_tree_sha"):
        value = metadata.get(field, "")
        if not SHA.fullmatch(value) or value == PLACEHOLDER_SHA:
            errors.append(f"{field} must be a non-placeholder full SHA")
    images = metadata.get("images", {})
    if not isinstance(images, dict) or set(images) != EXPECTED_SERVICES:
        errors.append("release metadata must contain exactly three deployable images")
        return errors
    for name in sorted(EXPECTED_SERVICES):
        image = images.get(name, {})
        digest = image.get("digest", "") if isinstance(image, dict) else ""
        repository = image.get("repository") if isinstance(image, dict) else None
        if repository != f"api-observatory/{name}":
            errors.append(f"{name}: repository does not match the service contract")
        if not DIGEST.fullmatch(digest) or digest == PLACEHOLDER_DIGEST:
            errors.append(f"{name}: digest must be a non-placeholder sha256 digest")
    return errors


def build_lock(
    metadata: dict[str, Any], current_lock: dict[str, Any]
) -> dict[str, Any]:
    """Build desired state while preserving the reviewed optional profile selection."""
    profiles = current_lock.get("enabled_profiles", [])
    if not isinstance(profiles, list):
        raise TypeError("current image lock enabled_profiles must be a list")
    if not set(profiles).issubset(SUPPORTED_PROFILES) or len(profiles) != len(
        set(profiles)
    ):
        raise ValueError(
            "current image lock contains unsupported or duplicate profiles"
        )
    return {
        "schema_version": 1,
        "source_commit_sha": metadata["source_commit_sha"],
        "source_tree_sha": metadata["source_tree_sha"],
        "enabled_profiles": profiles,
        "images": metadata["images"],
    }


def write_lock(path: Path, lock: dict[str, Any]) -> None:
    """Replace the lock atomically without changing its existing mode."""
    mode = stat.S_IMODE(path.stat().st_mode)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(lock, temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, mode)
    os.replace(temporary_path, path)


def promote(metadata: dict[str, Any], lock_path: Path = DEFAULT_LOCK) -> None:
    """Validate release metadata and write the updated image lock."""
    errors = validate_metadata(metadata)
    if errors:
        raise ValueError("; ".join(errors))
    current_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    write_lock(lock_path, build_lock(metadata, current_lock))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        parser.error("release metadata must be a JSON object")
    promote(metadata, args.lock)
    print(f"Updated {args.lock}; review and commit the desired-state diff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
