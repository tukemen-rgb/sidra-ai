"""C-1846: a deck admits when none of its evidence is about the subject.

The deck twin of C-1532. A fact matching a slide's section cue is placed on that
slide even when it does not mention the deck's subject, so a 「量子コンピュータ」 deck
read as backed by a 「定着率」 fact with no caveat. The deck now carries the same
subject-mismatch admission the report does — but only when facts were placed, and
without dropping them (C-1403).
"""

from __future__ import annotations

from sidra_ai.creation.decks import generate_deck
from sidra_ai.creation.evidence import Fact
from sidra_ai.evals.deck_discloses_subject_unmatched import (
    evaluate_deck_discloses_subject_unmatched,
)

_CAVEAT = "主題との重なりは確認できていません"
_RETENTION = Fact("主要課題はユーザー定着率である", "owner/repo docs/x.md")


def test_deck_subject_eval_passes():
    result = evaluate_deck_discloses_subject_unmatched()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


def test_off_subject_deck_discloses_and_keeps_the_fact():
    deck = generate_deck("量子コンピュータのスライドを作って", facts=[_RETENTION])
    assert _CAVEAT in deck.html
    assert "主題についての根拠として読まないでください" in deck.html
    # The fact is disclosed as off-subject, not silently dropped (C-1403).
    assert "定着率" in deck.html


def test_on_subject_deck_has_no_caveat():
    deck = generate_deck("定着率のスライドを作って", facts=[_RETENTION])
    assert _CAVEAT not in deck.html
    assert "定着率" in deck.html


def test_empty_deck_has_no_subject_caveat():
    deck = generate_deck("量子コンピュータのスライドを作って", facts=[])
    assert _CAVEAT not in deck.html
