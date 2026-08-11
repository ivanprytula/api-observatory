# Agent Evaluation Suite

The `services/ingestor/agent/evals/` folder contains deterministic, offline
quality checks for the LangGraph incident-triage agent. It is a public record
of the agent's expected behavior and a regression guard.

## Contents

| Path | Purpose |
| --- | --- |
| `evaluator.py` | Loads golden cases, runs deterministic checks, produces a report |
| `schemas.py` | Pydantic models for `AgentEvalCase`, `AgentEvalDataset`, `AgentEvalReport` |
| `fixtures/` | Versioned JSON datasets of reviewed agent outputs |
| `__init__.py` | Exports `evaluate_cases` and `load_cases` |

## How It Works

1. A **golden dataset** is a JSON file containing recorded agent outputs for
   known incidents. Each case includes:
   - `input`: the incident context (severity, summary, guidance, etc.)
   - `expected`: explicit quality anchors (minimum confidence, expected severity)
   - `actual`: the agent's recorded output

2. `load_cases(path)` validates the dataset against `AgentEvalDataset`.

3. `evaluate_case(case)` runs deterministic checks:
   - `severity_matches` — actual severity equals expected severity
   - `severity_reasoning_present` — reasoning text exceeds minimum length
   - `confidence_meets_minimum` — confidence score meets threshold
   - `action_present` — recommended action text exceeds minimum length

4. `evaluate_cases(dataset)` aggregates per-case results into an
   `AgentEvalReport` with pass/fail counts and an overall score.

## Running Evals

```bash
uv run pytest services/ingestor/tests/unit/agent/test_evals.py -v
```

Or programmatically:

```python
from pathlib import Path
from services.ingestor.agent.evals import load_cases, evaluate_cases

dataset = load_cases(Path("services/ingestor/agent/evals/fixtures/incidents.json"))
report = evaluate_cases(dataset)
print(f"Passed: {report.passed}/{report.total}")
```

## Adding New Cases

1. Generate a real agent run for a known incident (or use a recorded fixture).
2. Create a JSON entry with `input`, `expected`, and `actual`.
3. Add the case to a fixture file under `fixtures/`.
4. Run the eval suite to verify the new case passes.

## Limitations

- Evals are **deterministic**, not probabilistic. They check structure and
  thresholds, not semantic quality.
- The agent is gated behind `ANTHROPIC_ENABLED=true` and an API key. Evals
  can run against recorded fixtures without an API key.
- Fixtures are versioned manually. There is no auto-generated golden set.
