#!/usr/bin/env python3
"""Build the AWS MVP SSM deployment payload."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def build_ssm_payload(
    lock_path: Path,
    registry: str,
    instance_id: str,
    contract_version: str,
    compose_path: Path,
    prometheus_path: Path,
    rollout_path: Path,
    alb_target_group_arn: str | None = None,
) -> dict[str, object]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    lines: list[str] = []
    for name in sorted(lock.get("images", {})):
        image = lock["images"][name]
        if isinstance(image, dict):
            repository = image.get("repository", "")
            digest = image.get("digest", "")
            lines.append(f"{name.upper()}_IMAGE={registry}/{repository}@{digest}")
    lines.append(f"SERVICE_VERSION=tree-{lock['source_tree_sha']}")
    profiles = lock.get("enabled_profiles", [])
    if isinstance(profiles, list):
        lines.append(f"ENABLED_PROFILES={','.join(profiles)}")
    if alb_target_group_arn:
        lines.append(f"ALB_TARGET_GROUP_ARN={alb_target_group_arn}")

    deployment_env = base64.b64encode("\n".join(lines).encode("utf-8")).decode("ascii")

    version_check = (
        f'test "$(head -n 1 /opt/api-observatory-mvp/.platform-contract-version)" '
        f'= "{contract_version}"'
    )
    render = (
        "/usr/local/sbin/api-observatory-mvp-render-env "
        "ingestor-db ingestor dashboard cache backup"
    )
    commands = [
        version_check,
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
        render,
        "./rollout.sh",
    ]

    return {"commands": commands, "instanceIds": [instance_id]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SSM payload for AWS MVP deploy")
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--registry", type=str, required=True)
    parser.add_argument("--instance-id", type=str, required=True)
    parser.add_argument("--contract-version", type=str, required=True)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--prometheus", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alb-target-group-arn", type=str, default=None)
    args = parser.parse_args()

    payload = build_ssm_payload(
        args.lock,
        args.registry,
        args.instance_id,
        args.contract_version,
        args.compose,
        args.prometheus,
        args.rollout,
        args.alb_target_group_arn,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"payload_path={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
