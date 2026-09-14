"""C-1793: a deck discloses a substituted structure, not just silently uses pitch.

A request for a structure the deck cannot build (「SWOT」「タイムライン」) is
answered with the pitch template; the deck HTML and the chat summary now both
carry outline_fallback_note, while a bare request or a buildable shape
(週報→status) adds no such note and the deck's own footer stays intact.
"""

from __future__ import annotations

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.deck_discloses_outline_fallback import (
    evaluate_deck_discloses_outline_fallback,
)
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "代わりに標準の"


def test_deck_outline_fallback_eval_passes():
    result = evaluate_deck_discloses_outline_fallback()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_an_unbuildable_structure_is_disclosed_on_the_deck():
    html = generate_deck("SWOT分析のスライドを作って").html
    assert _NOTE in html
    assert "推測で埋めません" in html  # the deck's own footer still stands


def test_a_bare_request_adds_no_note():
    assert _NOTE not in generate_deck("スライドを作って").html


def test_a_buildable_structure_adds_no_note():
    assert _NOTE not in generate_deck("週報のスライドを作って").html


def test_the_chat_summary_discloses_the_substitution():
    gen = build_deck_generator(scratch_dir())
    req = "タイムラインのスライドを作って"
    outcome = gen(req, detect_creation_intent(req))
    assert _NOTE in (outcome.summary or "")
