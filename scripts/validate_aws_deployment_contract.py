"""Validate the AWS Stage-0 manifest and Compose delivery interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "infra/deployment/aws-stage0-services.json"
STAGE0_COMPOSE_PATH = PROJECT_ROOT / "docker-compose.aws-stage0.yml"


def validate() -> list[str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    stage0_compose = STAGE0_COMPOSE_PATH.read_text(encoding="utf-8")
    errors: list[str] = []

    if manifest.get("deployment_target") != "aws-stage0-ec2-compose":
        errors.append("deployment target must be aws-stage0-ec2-compose")
    if manifest.get("registry_variable") != "AWS_ECR_REGISTRY":
        errors.append("registry variable must be AWS_ECR_REGISTRY")
    if manifest.get("image_tag_template") != "tree-{full_tree_sha}":
        errors.append("image tag template must be tree-{full_tree_sha}")
    if manifest.get("image_reference_format") != "{repository}@{digest}":
        errors.append("image references must use repository digests")
    if manifest.get("compose_file") != "docker-compose.aws-stage0.yml":
        errors.append("AWS Stage 0 must use docker-compose.aws-stage0.yml")

    for service in manifest.get("services", []):
        name = service["name"]
        for required_key in (
            "image_repository",
            "dockerfile",
            "build_context",
            "port",
            "health_path",
            "readiness_path",
        ):
            if not service.get(required_key):
                errors.append(f"{name}: missing {required_key}")
        image_variable = f"${{{name.upper()}_IMAGE:?Set {name.upper()}_IMAGE"
        if image_variable not in stage0_compose:
            errors.append(
                f"{name}: Stage 0 Compose does not require an immutable image"
            )

    if "INFERENCE_DATABASE_URL" not in stage0_compose:
        errors.append("Stage 0 Compose must use a distinct inference database URL")
    for service in ("ingestor", "inference"):
        migration_command = (
            f"{service}: docker compose run --rm --no-deps {service} "
            "alembic upgrade head"
        )
        if migration_command not in stage0_compose:
            errors.append(
                f"Stage 0 Compose must declare the {service} migration command"
            )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AWS deployment contract validation failed:", file=sys.stderr)
        print(*[f"- {error}" for error in errors], sep="\n", file=sys.stderr)
        return 1
    print("AWS deployment contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
