#!/usr/bin/env python3
"""Resolve application ref and build AWS MVP deployment payload."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _is_sha(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def resolve_ref(lock_path: Path) -> str:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source_commit_sha = lock["source_commit_sha"]
    source_tree_sha = lock["source_tree_sha"]
    if not _is_sha(source_commit_sha) or not _is_sha(source_tree_sha):
        raise ValueError("Lock file contains placeholder or invalid SHAs")
    if source_commit_sha == "0" * 40 or source_tree_sha == "0" * 40:
        raise ValueError("Lock file has not been promoted yet")
    return source_commit_sha


def build_runtime_groups(profiles: list[str]) -> list[str]:
    groups = ["ingestor-db", "ingestor", "dashboard", "backup"]
    if "inference" in profiles:
        groups.extend(["inference-db", "inference"])
    if "cache" in profiles:
        groups.append("cache")
    return groups


def build_deployment_env(lock: dict[str, Any], registry: str) -> str:
    tree_sha = lock["source_tree_sha"]
    lines: list[str] = []
    images = lock.get("images", {})
    if not isinstance(images, dict):
        raise TypeError("Lock file images must be a dict")
    for name in sorted(images):
        image = images[name]
        if not isinstance(image, dict):
            continue
        repository = image.get("repository", "")
        digest = image.get("digest", "")
        lines.append(f"{name.upper()}_IMAGE={registry}/{repository}@{digest}")
    lines.append(f"SERVICE_VERSION=tree-{tree_sha}")
    enabled_profiles = lock.get("enabled_profiles", [])
    if isinstance(enabled_profiles, list):
        lines.append(f"ENABLED_PROFILES={','.join(enabled_profiles)}")
    return base64.b64encode("\n".join(lines).encode("utf-8")).decode("ascii")


def verify_ecr_digests(lock: dict[str, Any], tree_sha: str) -> None:
    images = lock.get("images", {})
    if not isinstance(images, dict):
        raise TypeError("Lock file images must be a dict")
    for _name, image in images.items():
        if not isinstance(image, dict):
            continue
        repository = image.get("repository", "")
        digest = image.get("digest", "")
        tags = _run(
            [
                "aws",
                "ecr",
                "describe-images",
                "--repository-name",
                repository,
                "--image-ids",
                f"imageDigest={digest}",
                "--query",
                "imageDetails[0].imageTags",
                "--output",
                "text",
            ]
        )
        if f"tree-{tree_sha}" not in tags.split():
            raise RuntimeError(
                f"ECR image {repository}@{digest} missing expected tag tree-{tree_sha}"
            )


def build_ssm_parameters(
    lock_path: Path,
    registry: str,
    instance_id: str,
    contract_version: str,
    compose_path: Path,
    prometheus_path: Path,
    rollout_path: Path,
) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    verify_ecr_digests(lock, lock["source_tree_sha"])

    deployment_env = build_deployment_env(lock, registry)
    runtime_groups = build_runtime_groups(
        lock.get("enabled_profiles", [])
        if isinstance(lock.get("enabled_profiles"), list)
        else []
    )
    renderer_command = (
        f"/usr/local/sbin/api-observatory-mvp-render-env {' '.join(runtime_groups)}"
    )

    commands = [
        f'test "$(head -n 1 /opt/api-observatory-mvp/.platform-contract-version)" '
        f'= "{contract_version}"',
        "install -d -m 0700 /opt/api-observatory-mvp/.runtime",
        "cd /opt/api-observatory-mvp",
        "test ! -f .runtime/deployment.env || "
        "cp .runtime/deployment.env .runtime/deployment.env.previous",
        f"echo {deployment_env} | base64 -d > .runtime/deployment.env",
        "chmod 0600 .runtime/deployment.env",
        f"echo {base64.b64encode(compose_path.read_bytes()).decode('ascii')} "
        "| base64 -d > docker-compose.yml",
        f"echo {base64.b64encode(prometheus_path.read_bytes()).decode('ascii')} "
        "| base64 -d > prometheus.yml",
        f"echo {base64.b64encode(rollout_path.read_bytes()).decode('ascii')} "
        "| base64 -d > rollout.sh",
        "chmod 0700 rollout.sh",
        renderer_command,
        "./rollout.sh",
    ]

    return {
        "commands": commands,
        "instanceIds": [instance_id],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AWS MVP deployment helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser(
        "resolve-ref", help="Output source_commit_sha from lock file"
    )
    resolve_parser.add_argument("--lock", type=Path, required=True)

    payload_parser = subparsers.add_parser(
        "build-ssm-payload", help="Build SSM command parameters"
    )
    payload_parser.add_argument("--lock", type=Path, required=True)
    payload_parser.add_argument("--registry", type=str, required=True)
    payload_parser.add_argument("--instance-id", type=str, required=True)
    payload_parser.add_argument("--contract-version", type=str, required=True)
    payload_parser.add_argument("--compose", type=Path, required=True)
    payload_parser.add_argument("--prometheus", type=Path, required=True)
    payload_parser.add_argument("--rollout", type=Path, required=True)
    payload_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.command == "resolve-ref":
        ref = resolve_ref(args.lock)
        print(f"ref={ref}")
    elif args.command == "build-ssm-payload":
        payload = build_ssm_parameters(
            args.lock,
            args.registry,
            args.instance_id,
            args.contract_version,
            args.compose,
            args.prometheus,
            args.rollout,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"payload_path={args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
