#!/usr/bin/env python3
"""Build, push, and record release metadata for deployable images."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_VERSION_FILE = ROOT / "libs" / "contracts" / "VERSION"


def _read_contracts_version() -> str:
    return CONTRACTS_VERSION_FILE.read_text(encoding="utf-8").strip()


def _build_push_and_digest(
    service: dict[str, object],
    registry: str,
    tree_sha: str,
    contracts_version: str,
) -> tuple[str, str]:
    name = service["name"]
    dockerfile = service["dockerfile"]
    context = service["build_context"]
    repository = f"api-observatory/{name}"
    image = f"{registry}/{repository}:tree-{tree_sha}"

    build_args = [
        "docker",
        "build",
        "--file",
        str(dockerfile),
        "--tag",
        image,
        "--build-arg",
        f"CONTRACTS_VERSION={contracts_version}",
        str(context),
    ]
    _run(build_args)
    _run(["docker", "push", image])

    digest = _run(
        [
            "aws",
            "ecr",
            "describe-images",
            "--repository-name",
            repository,
            "--image-ids",
            f"imageTag=tree-{tree_sha}",
            "--query",
            "imageDetails[0].imageDigest",
            "--output",
            "text",
        ]
    )

    if not digest or digest == "None":
        raise RuntimeError(f"Failed to resolve ECR digest for {image}")

    return repository, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish release images and emit metadata",
    )
    parser.add_argument("--services", type=Path, required=True)
    parser.add_argument("--registry", type=str, required=True)
    parser.add_argument("--commit-sha", type=str, required=True)
    parser.add_argument("--tree-sha", type=str, required=True)
    parser.add_argument(
        "--summary-file", type=Path, help="GitHub Actions step summary file"
    )
    args = parser.parse_args(argv)

    services_doc = json.loads(args.services.read_text(encoding="utf-8"))
    contracts_version = _read_contracts_version()

    metadata: dict[str, object] = {
        "schema_version": 1,
        "source_repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "source_commit_sha": args.commit_sha,
        "source_tree_sha": args.tree_sha,
        "contracts_version": contracts_version,
        "images": {},
    }

    for service in services_doc["services"]:
        name = service["name"]
        repository, digest = _build_push_and_digest(
            service, args.registry, args.tree_sha, contracts_version
        )
        metadata["images"][name] = {"repository": repository, "digest": digest}

        if args.summary_file:
            args.summary_file.parent.mkdir(parents=True, exist_ok=True)
            with open(args.summary_file, "a", encoding="utf-8") as handle:
                handle.write(f"{name}={args.registry}/{repository}@{digest}\n")

    expected = len(services_doc["services"])
    actual = len(metadata["images"])
    if actual != expected:
        raise RuntimeError(f"Expected {expected} images but produced {actual}")

    metadata_path = (
        Path(tempfile.gettempdir()) / f"release-metadata-{args.tree_sha}.json"
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    encoded = base64.b64encode(metadata_path.read_bytes()).decode("ascii")

    print(f"tree_sha={args.tree_sha}")
    print(f"metadata_path={metadata_path}")
    print(f"metadata={encoded}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
