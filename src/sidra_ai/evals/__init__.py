"""Security/behaviour eval suite. Runs offline, with no model weights."""

from sidra_ai.evals.cases import GATE_CASES, EvalOutcome, GateCase
from sidra_ai.evals.runner import EvalReport, run_all, run_gate_case

__all__ = [
    "GATE_CASES",
    "EvalOutcome",
    "EvalReport",
    "GateCase",
    "run_all",
    "run_gate_case",
]
