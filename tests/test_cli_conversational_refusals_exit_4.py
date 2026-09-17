"""C-1931: every conversational refusal exits 4, not 1 (outage).

how_to_make (C-1875) was added to the service without being added to
_CONVERSATIONAL_REFUSALS, so "レポートの作り方を教えて" exited 1 - an API-outage
code a monitor pages on. Every conversational code now exits 4; safety stays 3,
outage 1, answered 0.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.ask_cli import _CONVERSATIONAL_REFUSALS, render
from sidra_ai.evals.cli_conversational_refusals_exit_4 import (
    CONVERSATIONAL_CODES,
    evaluate_cli_conversational_refusals_exit_4,
)


def test_eval_passes():
    result = evaluate_cli_conversational_refusals_exit_4()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 30


def test_how_to_make_is_conversational():
    assert "how_to_make" in _CONVERSATIONAL_REFUSALS


@pytest.mark.parametrize("code", CONVERSATIONAL_CODES)
def test_each_conversational_code_exits_4(code):
    payload = {"refused": True, "answer": "…", "refusal": code,
               "security": {"decision": "allow"}, "citations": []}
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        assert render(dict(payload)) == 4


def test_outage_still_exits_1():
    payload = {"refused": True, "answer": "", "refusal": "model_unavailable",
               "security": {"decision": "allow"}, "citations": []}
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        assert render(dict(payload)) == 1
