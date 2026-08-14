import base64
import json
import tempfile
from pathlib import Path

import pytest

from scripts.ci import deploy_ssm, promote_lock


pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def release_metadata() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_commit_sha": "1" * 40,
        "source_tree_sha": "2" * 40,
        "contracts_version": "1.0.0",
        "images": {
            name: {
                "repository": f"api-observatory/{name}",
                "digest": f"sha256:{value * 64}",
            }
            for name, value in (
                ("ingestor", "3"),
                ("inference", "4"),
                ("dashboard", "5"),
                ("cache", "6"),
            )
        },
    }


def test_promote_lock_merges_metadata_and_preserves_profiles() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump({"enabled_profiles": ["inference", "monitoring"]}, handle)
        lock_path = Path(handle.name)

    try:
        promote_lock.promote(release_metadata(), lock_path)
        result = json.loads(lock_path.read_text(encoding="utf-8"))
        assert result["source_commit_sha"] == "1" * 40
        assert result["source_tree_sha"] == "2" * 40
        assert result["contracts_version"] == "1.0.0"
        assert result["enabled_profiles"] == ["inference", "monitoring"]
        assert set(result["images"]) == {"ingestor", "inference", "dashboard", "cache"}
    finally:
        lock_path.unlink(missing_ok=True)


def test_promote_lock_writes_atomically() -> None:
    with tempfile.TemporaryDirectory() as directory:
        lock_path = Path(directory) / "images.lock.json"
        lock_path.write_text('{"enabled_profiles": []}\n', encoding="utf-8")
        promote_lock.promote(release_metadata(), lock_path)
        result = json.loads(lock_path.read_text(encoding="utf-8"))
        assert result["images"]["ingestor"]["digest"].startswith("sha256:")
        assert result["images"]["cache"]["digest"].startswith("sha256:")


def test_deploy_ssm_payload_shape() -> None:
    with tempfile.TemporaryDirectory() as directory:
        lock_path = Path(directory) / "lock.json"
        lock_path.write_text(json.dumps(release_metadata()), encoding="utf-8")
        compose = Path(directory) / "compose.yml"
        compose.write_text("services: {}", encoding="utf-8")
        prometheus = Path(directory) / "prometheus.yml"
        prometheus.write_text("", encoding="utf-8")
        rollout = Path(directory) / "rollout.sh"
        rollout.write_text("#!/usr/bin/env bash\necho ok", encoding="utf-8")

        payload = deploy_ssm.build_ssm_payload(
            lock_path=lock_path,
            registry="123456789012.dkr.ecr.eu-central-1.amazonaws.com",
            instance_id="i-1234567890abcdef0",
            contract_version="1",
            compose_path=compose,
            prometheus_path=prometheus,
            rollout_path=rollout,
            alb_target_group_arn="arn:aws:elasticloadbalancing:eu-central-1:123456789012:targetgroup/api-observatory/abc123",
        )

        assert payload["instanceIds"] == ["i-1234567890abcdef0"]
        assert len(payload["commands"]) >= 10
        for cmd in payload["commands"]:
            if "echo" in cmd and "base64 -d > .runtime/deployment.env" in cmd:
                b64 = cmd.split("echo ")[1].split(" | base64")[0]
                env_text = base64.b64decode(b64).decode("utf-8")
                break
        else:
            pytest.fail("deployment.env command not found in payload")
        assert "CACHE_IMAGE=" in env_text
        assert "ALB_TARGET_GROUP_ARN=" in env_text
        assert any("rollout.sh" in cmd for cmd in payload["commands"])


def test_source_publishes_then_updates_one_app_owned_promotion_pr() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    publisher = (WORKFLOWS / "publish-images.yml").read_text(encoding="utf-8")

    assert "workflow_call:" in publisher
    assert "workflow_dispatch:" in publisher
    assert "vars.AWS_IMAGE_PUBLISH_ENABLED == 'true'" in publisher
    assert "Only the current main commit may be published." in publisher
    assert "A newer main commit superseded this release" in publisher
    assert "APP_PROMOTION_TOKEN is required" in publisher
    assert "scripts/ci/promote_lock.py" in publisher
    assert "automation/promote-aws-dev" in publisher
    assert ".infra-promotion" not in publisher
    assert "repository_dispatch" not in publisher
    assert "deployable_images: ${{ steps.filter.outputs.deployable_images }}" in ci
    assert (
        "needs: [changes, code-quality, docs-quality, unit, integration, image-smoke]"
        in ci
    )
    assert "needs.changes.outputs.deployable_images == 'true'" in ci
    assert "uses: ./.github/workflows/publish-images.yml" in ci
    assert ci.count("uses: ./.github/workflows/publish-images.yml") == 1


def test_promotion_cannot_assume_deployment_credentials() -> None:
    publisher = (WORKFLOWS / "publish-images.yml").read_text(encoding="utf-8")
    promote_job = publisher.split("  promote:", maxsplit=1)[1]

    assert "id-token: write" not in promote_job
    assert "configure-aws-credentials" not in promote_job


def test_deploy_workflow_uses_simplified_scripts() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    deployment = (WORKFLOWS / "deploy-aws-mvp.yml").read_text(encoding="utf-8")
    deploy_script = (ROOT / "scripts/ci/deploy_ssm.py").read_text(encoding="utf-8")

    assert "aws_mvp_lock:" in ci
    assert "'environments/aws-dev/images.lock.json'" in ci
    assert "needs.changes.outputs.aws_mvp_lock == 'true'" in ci
    assert "uses: ./.github/workflows/deploy-aws-mvp.yml" in ci
    assert ci.count("uses: ./.github/workflows/deploy-aws-mvp.yml") == 1
    assert "workflow_call:" in deployment
    assert "workflow_dispatch:" in deployment
    assert "vars.AWS_CD_ENABLED == 'true'" in deployment
    assert "vars.AWS_APP_DEPLOY_ROLE_ARN" in deployment
    assert "environments/aws-dev/images.lock.json" in deployment
    assert "aws ssm send-command" in deployment
    assert "contracts_version" in deployment
    assert (
        "api-observatory-mvp-render-env" in deployment
        or "api-observatory-mvp-render-env" in deploy_script
    )
    assert (
        ".platform-contract-version" in deployment
        or ".platform-contract-version" in deploy_script
    )
    assert "repository_dispatch:" not in deployment
    assert "github.event.client_payload" not in deployment
    assert "contents: write" not in deployment
    assert "git commit" not in deployment
    assert "git push" not in deployment


def test_docs_and_desired_state_do_not_publish_or_smoke_build_images() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    deployable_filter = ci.split("deployable_images:", maxsplit=1)[1].split(
        "aws_mvp_lock:", maxsplit=1
    )[0]

    assert "docs/" not in deployable_filter
    assert "environments/" not in deployable_filter
    assert "deployment/" not in deployable_filter
    assert "!services/mcp/**" in ci
    assert "needs.changes.outputs.deployable_images == 'true'" in ci
