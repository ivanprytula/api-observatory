"""Validate the AWS Stage-0 deployment manifest against CI image jobs."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "infra/deployment/aws-stage0-services.json"
CI_WORKFLOW_PATH = PROJECT_ROOT / ".github/workflows/ci.yml"


def validate() -> list[str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ci_workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []

    if manifest.get("deployment_target") != "aws-stage0-ec2-compose":
        errors.append("deployment target must be aws-stage0-ec2-compose")
    if manifest.get("registry_variable") != "AWS_ECR_REGISTRY":
        errors.append("registry variable must be AWS_ECR_REGISTRY")
    if manifest.get("image_tag_template") != "tree-{tree_sha}":
        errors.append("image tag template must be tree-{tree_sha}")

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
        if f"docker-build-{name}:" not in ci_workflow:
            errors.append(f"{name}: missing docker-build-{name} CI job")
        if service["image_repository"] not in ci_workflow:
            errors.append(f"{name}: image repository is absent from CI")
        if service["dockerfile"] not in ci_workflow:
            errors.append(f"{name}: Dockerfile is absent from CI")

    if "tree-${TREE_SHA}" not in ci_workflow:
        errors.append("CI does not use the immutable tree SHA tag")
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
