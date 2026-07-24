import runpy
from pathlib import Path


def test_aws_deployment_contract_matches_ci_image_jobs() -> None:
    script = Path(__file__).parents[2] / "scripts/validate_aws_deployment_contract.py"
    validate = runpy.run_path(script)["validate"]
    assert validate() == []
