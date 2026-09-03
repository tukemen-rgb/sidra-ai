"""C-1217: deck bullets end at a sentence, not a 120-character cliff.

A requested revenue deck's one filled slide carried three bullets and all
three ended mid-word (「…（components/UploadForm.ts」). ``_bullets_for``
re-cut already-trimmed facts at a hard 120 characters - the second cut
site of the failure C-1213 fixed at the first - and ``whole_sentences``
counted the dot inside 「revenue-model.md」 as a sentence end.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import whole_sentences
from sidra_ai.evals.deck_bullet_sentences import evaluate_deck_bullet_sentences


def test_deck_bullet_sentences_eval_passes():
    result = evaluate_deck_bullet_sentences()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 7


def test_filename_dot_is_not_a_sentence_end():
    text = (
        "この一覧の続きは収益方針の本文の脇に置かれたファイルにあって名前は "
        "revenue-model.md というもの"
    )
    assert whole_sentences(text) == text


def test_ascii_sentence_end_still_cuts():
    text = (
        "This problem statement about the deck generator ends properly. "
        "Trailing filler that should be trimmed away"
    )
    assert whole_sentences(text).endswith("properly.")
