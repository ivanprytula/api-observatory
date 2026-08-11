import json
import runpy
import tempfile
from pathlib import Path

import pytest

from scripts import promote_mvp_images


pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def release_metadata() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_repository": "ivanprytula/api-observatory",
        "source_commit_sha": "1" * 40,
        "source_tree_sha": "2" * 40,
        "images": {
            name: {
                "repository": f"api-observatory/{name}",
                "digest": f"sha256:{value * 64}",
            }
            for name, value in (
                ("ingestor", "3"),
                ("inference", "4"),
                ("dashboard", "5"),
            )
        },
    }


def test_release_manifest_and_mvp_contract_are_valid() -> None:
    release_main = runpy.run_path(ROOT / "scripts/validate_release_manifest.py")["main"]
    contract_main = runpy.run_path(ROOT / "scripts/validate_mvp_contract.py")["main"]

    assert release_main() == 0
    assert contract_main(["--allow-placeholder-lock", "--app-root", str(ROOT)]) == 0


def test_promotion_validates_metadata_and_preserves_profiles() -> None:
    metadata = release_metadata()
    first = promote_mvp_images.build_lock(
        metadata, {"enabled_profiles": ["inference", "monitoring"]}
    )
    duplicate = promote_mvp_images.build_lock(metadata, first)

    assert promote_mvp_images.validate_metadata(metadata) == []
    assert duplicate == first
    assert first["enabled_profiles"] == ["inference", "monitoring"]


def test_promotion_rejects_malformed_metadata_and_profiles() -> None:
    metadata = release_metadata()
    del metadata["images"]["dashboard"]  # type: ignore[index]

    assert "release metadata must contain exactly three deployable images" in (
        promote_mvp_images.validate_metadata(metadata)
    )
    with pytest.raises(ValueError, match="unsupported or duplicate profiles"):
        promote_mvp_images.build_lock(
            release_metadata(), {"enabled_profiles": ["unknown"]}
        )


def test_newer_release_supersedes_images_without_changing_profiles() -> None:
    current = promote_mvp_images.build_lock(
        release_metadata(), {"enabled_profiles": ["cache"]}
    )
    newer = release_metadata()
    newer["source_commit_sha"] = "6" * 40
    newer["source_tree_sha"] = "7" * 40
    newer["images"] = {
        name: {
            "repository": f"api-observatory/{name}",
            "digest": f"sha256:{value * 64}",
        }
        for name, value in (
            ("ingestor", "8"),
            ("inference", "9"),
            ("dashboard", "a"),
        )
    }

    promoted = promote_mvp_images.build_lock(newer, current)

    assert promoted["source_commit_sha"] == "6" * 40
    assert promoted["source_tree_sha"] == "7" * 40
    assert promoted["images"] != current["images"]
    assert promoted["enabled_profiles"] == current["enabled_profiles"]


def test_promotion_writes_only_the_lock() -> None:
    with tempfile.TemporaryDirectory() as directory:
        lock_path = Path(directory) / "images.lock.json"
        lock_path.write_text('{"enabled_profiles": []}\n', encoding="utf-8")
        expected = promote_mvp_images.build_lock(
            release_metadata(), {"enabled_profiles": []}
        )

        promote_mvp_images.write_lock(lock_path, expected)

        assert json.loads(lock_path.read_text(encoding="utf-8")) == expected


def test_source_publishes_then_updates_one_app_owned_promotion_pr() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    publisher = (WORKFLOWS / "publish-images.yml").read_text(encoding="utf-8")

    assert "workflow_call:" in publisher
    assert "workflow_dispatch:" in publisher
    assert "vars.AWS_IMAGE_PUBLISH_ENABLED == 'true'" in publisher
    assert "Only the current main commit may be published." in publisher
    assert "A newer main commit superseded this release" in publisher
    assert "APP_PROMOTION_TOKEN is required" in publisher
    assert "scripts/ci/promote_release.py" in publisher
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


def test_merged_lock_or_revert_invokes_one_committed_state_deployment() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    deployment = (WORKFLOWS / "deploy-aws-mvp.yml").read_text(encoding="utf-8")

    deploy_script = (ROOT / "scripts/ci/deploy_mvp.py").read_text(encoding="utf-8")

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
    assert "MVP_PLATFORM_CONTRACT_VERSION" in deployment
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
