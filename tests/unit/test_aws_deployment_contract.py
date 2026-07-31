import runpy
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_release_manifest_matches_delivery_contract() -> None:
    script = Path(__file__).parents[2] / "scripts/validate_release_manifest.py"
    main = runpy.run_path(script)["main"]
    assert main() == 0
