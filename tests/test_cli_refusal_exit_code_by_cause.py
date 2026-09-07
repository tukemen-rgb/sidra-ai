"""C-1456: sidra-ask gives a refusal the exit code that matches its cause.

Every refusal used to return 3, so a model-backend-unavailable outage (an
operational failure the docstring assigns to exit 1) came back under the code a
script uses for a policy refusal. The exit code now follows the cause.
"""

from __future__ import annotations

import io
import contextlib

import pytest

from sidra_ai.api.ask_cli import render
from sidra_ai.evals.cli_refusal_exit_code_by_cause import (
    evaluate_cli_refusal_exit_code_by_cause,
)


def _code(payload):
    with contextlib.redirect_stdout(io.StringIO()):
        return render(dict(payload))


def test_cli_refusal_exit_code_eval_passes():
    result = evaluate_cli_refusal_exit_code_by_cause()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_model_unavailable_is_operational_exit_one():
    payload = {
        "refused": True,
        "answer": "",
        "reason": "model backend unavailable",
        "security": {"decision": "allow"},
        "citations": [],
    }
    assert _code(payload) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"refused": True, "answer": "", "security": {"decision": "block"}, "citations": []},
        {"refused": True, "answer": "", "security": {"decision": "quarantine"}, "citations": []},
        {
            "refused": True,
            "answer": "",
            "reason": "model output withheld by security guard",
            "security": {"decision": "allow"},
            "model": {"backend": "echo"},
            "citations": [],
        },
    ],
)
def test_safety_refusals_stay_exit_three(payload):
    assert _code(payload) == 3
