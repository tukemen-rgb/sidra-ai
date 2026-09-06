"""C-1274: a deck discloses when the PowerPoint file could not be made.

Where python-pptx (an optional ``creation`` extra) is not installed, the deck
falls back to HTML only. The summary used to say only that the deck was made, so
someone who asked for slides received HTML and could not tell. It now says the
.pptx was skipped when it was, and stays silent when the .pptx was written.
"""

from __future__ import annotations

from sidra_ai.evals.deck_pptx_absence_disclosed import (
    _NOTE_MARKER,
    _build_service,
    evaluate_deck_pptx_absence_disclosed,
)


def test_deck_pptx_absence_disclosed_eval_passes():
    result = evaluate_deck_pptx_absence_disclosed()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 2


def test_summary_discloses_exactly_when_pptx_is_absent():
    svc = _build_service()
    result = svc.chat("売上のスライドを作って") or {}
    outcome = (result.get("creation") or {}).get("outcome") or {}
    answer = str(result.get("answer") or "")
    pptx_written = bool((outcome.get("details") or {}).get("pptx_path"))
    if pptx_written:
        assert _NOTE_MARKER not in answer
    else:
        # the deliverable the reader asked for was not produced - say so
        assert _NOTE_MARKER in answer
        assert "管理者" in answer  # framed as the administrator's action
