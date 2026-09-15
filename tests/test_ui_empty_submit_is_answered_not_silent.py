"""C-1874: an empty submit on the web page is answered, not met with silence.

The submit handler returned before any feedback on a blank or whitespace-only
box, though the page carries refusalMsg["empty"]. These tests pin that the empty
guard now writes the live status region from the single source and still returns
without sending a request, and that the C-1700 real-answer path is untouched.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_empty_submit_is_answered_not_silent import (
    evaluate_ui_empty_submit_is_answered_not_silent,
)


def _guard() -> str:
    handler = ASK_PAGE[ASK_PAGE.find('form.addEventListener("submit"'):]
    start = handler.find("if (!question)")
    end = handler.find("send.disabled = true", start)
    return handler[start:end]


def test_eval_passes():
    result = evaluate_ui_empty_submit_is_answered_not_silent()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_empty_guard_writes_status_and_returns():
    guard = _guard()
    assert "statusLine.textContent" in guard
    assert "return" in guard


def test_empty_guard_reuses_single_source():
    assert re.search(
        r'refusalMessage\(\s*\{\s*refusal:\s*"empty"\s*\}\s*\)', _guard()
    )


def test_status_region_is_a_live_region():
    assert 'id="status"' in ASK_PAGE
    assert 'role="status"' in ASK_PAGE
    assert 'aria-live="polite"' in ASK_PAGE
