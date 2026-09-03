"""C-1210: the ask page sends the conversation so follow-ups can retrieve.

The server has accepted screened history for weeks; the page sent
``{message}`` alone, so a browser 「それはなぜ？」 always abstained. The
conversation lives in a page variable (no browser storage - the posture is
pinned by the ask-page security tests), is bounded to the server's own
turn cap, and only successful exchanges join it.
"""

from __future__ import annotations

from sidra_ai.api.schemas import MAX_HISTORY_TURNS
from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_followup import evaluate_ui_followup


def test_payload_carries_the_conversation():
    assert "payload.history = turns.slice(-MAX_TURNS)" in ASK_PAGE
    assert "JSON.stringify(payload)" in ASK_PAGE


def test_turn_cap_matches_the_server():
    assert f"MAX_TURNS = {MAX_HISTORY_TURNS};" in ASK_PAGE


def test_only_successful_exchanges_join():
    assert "!result.refused" in ASK_PAGE


def test_storage_posture_survives():
    assert "localStorage" not in ASK_PAGE
    assert "sessionStorage" not in ASK_PAGE


def test_ui_followup_eval_passes():
    result = evaluate_ui_followup()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 5
