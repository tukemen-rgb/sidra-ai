"""C-1821: a deck asked for in five slides says it made four.

Both outlines are fixed at four sections; the request's number used to be read
by nobody. slide_count_note is the one source for the deck HTML and the chat
summary, silent when no size was asked for and when the size asked for is the
size that was built.
"""

from __future__ import annotations

from sidra_ai.creation.deck_job import build_deck_generator
from sidra_ai.creation.decks import (
    generate_deck,
    requested_slide_count,
    slide_count_note,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.deck_says_it_made_a_different_count import (
    evaluate_deck_says_it_made_a_different_count,
)
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "枚数は指定できません"


def test_deck_slide_count_eval_passes():
    result = evaluate_deck_says_it_made_a_different_count()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_a_size_that_was_not_built_is_disclosed_on_the_deck():
    deck = generate_deck("5枚のスライドを作って")
    assert _NOTE in deck.html
    assert f"{len(deck.slides)} 枚で作ります" in deck.html
    assert "推測で埋めません" in deck.html  # the deck's own footer still stands


def test_a_request_with_no_size_adds_no_note():
    assert _NOTE not in generate_deck("スライドを作って").html


def test_the_size_actually_built_adds_no_note():
    assert _NOTE not in generate_deck("4枚のスライドを作って").html


def test_the_chat_summary_discloses_the_count():
    gen = build_deck_generator(scratch_dir())
    req = "5枚のスライドを作って"
    outcome = gen(req, detect_creation_intent(req))
    assert _NOTE in (outcome.summary or "")


def test_the_structure_note_and_the_count_note_coexist():
    html = generate_deck("SWOT分析を5枚のスライドで作って").html
    assert _NOTE in html
    assert "代わりに標準の" in html


def test_a_number_that_is_not_a_size_is_not_a_request():
    assert requested_slide_count("5年計画のスライドを作って") is None
    assert requested_slide_count("2026年のスライドを作って") is None
    assert requested_slide_count("売上5%のスライドを作って") is None
    assert requested_slide_count("10ページのスライドを作って") == 10
    assert requested_slide_count("5枚のスライドを作って") == 5
    # Three digits: 「100枚」 is exactly the request the note exists for.
    assert requested_slide_count("100枚のスライドを作って") == 100


def test_the_note_names_the_count_it_was_given():
    note = slide_count_note("5枚のスライドを作って", 7)
    assert "5 枚" in note and "7 枚" in note
    assert slide_count_note("5枚のスライドを作って", 5) == ""
    assert slide_count_note("スライドを作って", 4) == ""
