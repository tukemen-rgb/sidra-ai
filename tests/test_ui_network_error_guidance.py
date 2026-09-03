"""C-1218: a request that never reaches the server must say so in Japanese.

C-1211 translated HTTP status codes, but a fetch that gets no response at
all rejects with a ``TypeError`` whose message is an English browser string
(「Failed to fetch」). The catch blocks showed it verbatim - 「失敗: Failed
to fetch」 in an all-Japanese UI, with no hint to start the server.
``reason(error)`` now maps the network rejection to Japanese guidance while
HTTP-status errors (already Japanese) pass through unchanged.
"""

from __future__ import annotations

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_network_error_guidance import (
    evaluate_ui_network_error_guidance,
)


def test_ui_network_error_guidance_eval_passes():
    result = evaluate_ui_network_error_guidance()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_every_catch_site_routes_through_reason():
    # No catch block may print a raw error.message again.
    assert "+ error.message" not in ASK_PAGE
    assert ASK_PAGE.count("+ reason(error)") >= 5


def test_reason_keeps_translated_http_text():
    # reason() must not swallow our own (already-Japanese) HTTP messages.
    assert "return error.message;" in ASK_PAGE
    assert "function explain(status)" in ASK_PAGE
