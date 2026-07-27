#!/usr/bin/env python3
"""Validate the monorepo's workspace and independently deployable service manifests."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_MANIFEST = REPO_ROOT / "pyproject.toml"
LOCKFILE = REPO_ROOT / "uv.lock"
REQUIRED_METADATA = ("authors", "maintainers", "license")
SERVICE_NAME_OVERRIDES = {"mcp": "mcp-server"}


def load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def main() -> int:
    errors: list[str] = []
    root = load_toml(ROOT_MANIFEST)
    workspace = root.get("tool", {}).get("uv", {}).get("workspace", {})
    workspace_members = set(workspace.get("members", []))

    service_manifests = sorted((REPO_ROOT / "services").glob("*/pyproject.toml"))
    expected_members = {
        path.parent.relative_to(REPO_ROOT).as_posix() for path in service_manifests
    }
    if workspace_members != expected_members:
        errors.append(
            "workspace members do not match service manifests: "
            f"declared={sorted(workspace_members)}, discovered={sorted(expected_members)}"
        )

    if not LOCKFILE.exists():
        errors.append("uv.lock is missing")
        lock_packages: dict[str, dict] = {}
    else:
        lock = load_toml(LOCKFILE)
        lock_packages = {
            package.get("name"): package
            for package in lock.get("package", [])
            if package.get("source", {}).get("virtual")
        }

    for manifest in service_manifests:
        service_dir = manifest.parent
        service_name = service_dir.name
        project = load_toml(manifest).get("project", {})
        package_name = project.get("name")
        expected_name = SERVICE_NAME_OVERRIDES.get(service_name, service_name)

        if package_name != expected_name:
            errors.append(
                f"{manifest.relative_to(REPO_ROOT)}: name {package_name!r} "
                f"does not match expected {expected_name!r}"
            )

        for field in REQUIRED_METADATA:
            if not project.get(field):
                errors.append(
                    f"{manifest.relative_to(REPO_ROOT)}: missing project.{field}"
                )

        relative_service = service_dir.relative_to(REPO_ROOT).as_posix()
        relative_manifest = manifest.relative_to(REPO_ROOT).as_posix()
        if relative_service not in workspace_members:
            errors.append(f"{relative_service} is not a workspace member")

        if package_name not in lock_packages:
            errors.append(
                f"{manifest.relative_to(REPO_ROOT)} has no matching virtual uv.lock package"
            )

        dockerfile = service_dir / "Dockerfile"
        if dockerfile.exists() and relative_manifest not in dockerfile.read_text(
            encoding="utf-8"
        ):
            errors.append(
                f"{dockerfile.relative_to(REPO_ROOT)} does not reference {relative_manifest}"
            )

    if errors:
        print("Workspace manifest check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Workspace manifest check passed ({len(service_manifests)} services).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
