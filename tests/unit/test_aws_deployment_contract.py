import runpy
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


def test_release_manifest_matches_delivery_contract() -> None:
    script = ROOT / "scripts/validate_release_manifest.py"
    main = runpy.run_path(script)["main"]
    assert main() == 0


def test_ci_publishes_only_after_a_green_deployable_main_change() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    publisher = (ROOT / ".github/workflows/publish-images.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_call:" in publisher
    assert "workflow_dispatch:" in publisher
    assert "vars.AWS_IMAGE_PUBLISH_ENABLED == 'true'" in publisher
    assert "Only the current main commit may be published." in publisher
    assert "A newer main commit superseded this release" in publisher
    assert "deployable_images: ${{ steps.filter.outputs.deployable_images }}" in ci
    assert "needs: [changes, merge-gate]" in ci
    assert "github.event_name == 'push'" in ci
    assert "needs.changes.outputs.deployable_images == 'true'" in ci
    assert "uses: ./.github/workflows/publish-images.yml" in ci
    assert ci.count("uses: ./.github/workflows/publish-images.yml") == 1
    assert "peter-evans/create-pull-request@98357b18" in publisher
    assert "INFRA_PROMOTION_TOKEN is required" in publisher
    assert "repository_dispatch" not in publisher
    promote_job = publisher.split("  promote:", maxsplit=1)[1]
    assert "id-token: write" not in promote_job
    assert "configure-aws-credentials" not in promote_job


def test_docs_mcp_and_root_tests_are_not_deployable_image_paths() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    deployable_filter = ci.split("deployable_paths_regex=", maxsplit=1)[1].split(
        'if echo "$deployable_files"', maxsplit=1
    )[0]

    assert "services/)" in deployable_filter
    assert "libs/" in deployable_filter
    assert "grep -Ev '^services/mcp/'" in ci
    assert "docs/" not in deployable_filter
    assert "tests/" not in deployable_filter
    assert ".github/workflows/" not in deployable_filter
