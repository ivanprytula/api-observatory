import runpy
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_aws_deployment_contract_matches_delivery_workflows() -> None:
    script = Path(__file__).parents[2] / "scripts/validate_aws_deployment_contract.py"
    validate = runpy.run_path(script)["validate"]
    assert validate() == []
