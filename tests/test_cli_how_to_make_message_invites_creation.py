"""C-1933: the CLI's how_to_make reply invites creation, not an outage retry.

C-1931 gave how_to_make exit 4; the message text was left in the outage
fallback ("回答を出せなかった。少し時間をおいて、もう一度試す。"). ask_cli's
messages dict now has a how_to_make entry, so the terminal line invites
creation instead of telling the reader to wait for a failure that will not pass.
"""

from __future__ import annotations

import contextlib
import io

from sidra_ai.api.ask_cli import render
from sidra_ai.evals.cli_how_to_make_message_invites_creation import (
    evaluate_cli_how_to_make_message_invites_creation,
)


def _render(payload: dict) -> tuple[str, int]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = render(dict(payload))
    return buf.getvalue(), code


def test_eval_passes():
    result = evaluate_cli_how_to_make_message_invites_creation()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 20


def test_how_to_make_invites_and_is_not_the_outage_line():
    payload = {"refused": True, "refusal": "how_to_make",
               "answer": "レポートはこの場で作れます。",
               "security": {"decision": "allow"}, "citations": []}
    text, code = _render(payload)
    assert "この場で作れる" in text
    assert "少し時間をおいて" not in text  # not the outage "wait and retry" line
    assert code == 4  # conversational, per C-1931


def test_unknown_code_still_reaches_the_outage_fallback():
    payload = {"refused": True, "refusal": "not_a_real_code", "answer": "",
               "security": {"decision": "allow"}, "citations": []}
    text, code = _render(payload)
    assert "少し時間をおいて" in text
    assert code == 1
