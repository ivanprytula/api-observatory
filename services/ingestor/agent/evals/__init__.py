"""Offline, deterministic quality evaluation for incident-triage outputs."""

from services.ingestor.agent.evals.evaluator import evaluate_cases, load_cases


__all__ = ["evaluate_cases", "load_cases"]
