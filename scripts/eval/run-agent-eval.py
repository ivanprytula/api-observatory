"""Run deterministic agent-evaluation fixtures without provider access or cost."""
# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET = (
    _PROJECT_ROOT / "services/ingestor/agent/evals/fixtures/incident-triage-v1.json"
)
sys.path.insert(0, str(_PROJECT_ROOT))

from services.ingestor.agent.evals import evaluate_cases, load_cases


def _parse_args() -> argparse.Namespace:
    """Parse the dataset and optional JSON report destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help="Path to a versioned golden incident JSON dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON evaluation report.",
    )
    return parser.parse_args()


def main() -> int:
    """Evaluate a recorded fixture and return a CI-friendly status code."""
    args = _parse_args()
    report = evaluate_cases(load_cases(args.dataset))
    report_json = json.dumps(report.model_dump(mode="json"), indent=2) + "\n"

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_json, encoding="utf-8")
    print(report_json, end="")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
