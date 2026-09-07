"""C-1478: a deck discloses evidence it left off every slide.

build_slides leaves a fact matching no section's cue off every slide - the
right conservative call - but did so silently, so a deck built from five facts
could show two and quietly drop three. The footer now discloses that some
evidence did not fit any slide, the way the report discloses its set-aside
evidence (C-1281); a deck that placed everything, or was handed nothing, stays
silent.
"""

from __future__ import annotations

from sidra_ai.creation.decks import generate_deck, validate_deck
from sidra_ai.creation.evidence import Fact, NUMBER
from sidra_ai.evals.deck_discloses_omitted_facts import (
    evaluate_deck_discloses_omitted_facts,
)

_NOTE = "どのスライドにも当てはまらなかった根拠は載せていません"


def test_deck_omitted_facts_eval_passes():
    result = evaluate_deck_discloses_omitted_facts()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_uncued_facts_are_disclosed_and_deck_still_validates():
    facts = [
        Fact("導入に時間がかかる課題がある。", "docs/a.md"),
        Fact("チームは新しいオフィスへ移転した。", "docs/c.md"),
        Fact("創業者は元料理人である。", "docs/d.md"),
    ]
    deck = generate_deck("提案スライドを作って", facts=facts, outline="pitch")
    assert _NOTE in deck.html
    # the disclosure carries no fabricated figure
    note_line = next(ln for ln in deck.html.splitlines() if _NOTE in ln)
    assert not NUMBER.findall(note_line.replace("SIDRA", ""))
    assert validate_deck(deck, facts)["usable"]


def test_deck_that_placed_everything_stays_silent():
    facts = [Fact("導入に時間がかかる課題がある。", "docs/a.md"),
             Fact("検索機能を実装して解決した。", "docs/b.md")]
    deck = generate_deck("提案スライドを作って", facts=facts, outline="pitch")
    assert _NOTE not in deck.html


def test_empty_deck_stays_silent():
    deck = generate_deck("提案スライドを作って", facts=[], outline="pitch")
    assert _NOTE not in deck.html
