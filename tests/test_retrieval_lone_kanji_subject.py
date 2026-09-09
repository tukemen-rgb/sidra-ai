"""A subject written with one kanji must not be invisible.

「犬の飼い方のレポートを書いて」 named a subject that appeared in neither
subject unit. ``_SUBJECT_RUN`` needs two characters, and the bigram side
cannot help because ``_CJK_RUN`` spans hiragana: 「犬の飼い方」 yields 犬の /
の飼 / 飼い / い方 and every one is dropped for containing kana. Measured
2026-09-09: the report filter had nothing to judge with and kept five
unrelated facts under the word 「根拠」 (C-1512); the same hole let a revision
for 「猫のゲーム」 land on a different game (C-1511b).

Taking *every* lone kanji would be worse than the hole - 飼, 方 and 書 are
stems and tails of inflected words and would match almost any chunk. The
boundary rule tells them apart without a word list: a bare noun is not
preceded by kana and is followed by a particle or the end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.retrieval.search import subject_evidence_probes  # noqa: E402


def _windows(query: str) -> tuple[str, ...]:
    return subject_evidence_probes(query)[1]


@pytest.mark.parametrize(
    ("query", "subject"),
    [
        ("犬の飼い方のレポートを書いて", "犬"),
        ("猫のゲームを難しくして", "猫"),
        ("魚のゲームを作って", "魚"),
        ("犬", "犬"),
    ],
)
def test_a_one_character_subject_is_visible(query: str, subject: str) -> None:
    assert subject in _windows(query)


@pytest.mark.parametrize("stem", ["飼", "方", "書", "教"])
def test_the_inside_of_an_inflected_word_is_not_a_subject(stem: str) -> None:
    """The half that keeps the rule from being worse than the hole.

    These are all in 「犬の飼い方のレポートを書いて」 / 「作り方を教えて」 and
    all of them, as probes, would match chunks about anything at all.
    """

    windows = _windows("犬の飼い方のレポートを書いて") + _windows("作り方を教えて")

    assert stem not in windows


@pytest.mark.parametrize(
    "query",
    ["今週の進捗レポートを書いて", "この会社の株価を教えて", "ラーメンの作り方を教えて"],
)
def test_multi_character_subjects_are_unchanged(query: str) -> None:
    """Additive: the rule adds one-character subjects and touches nothing else."""

    windows = _windows(query)

    assert windows, "an existing subject must still be found"
    assert all(len(w) >= 2 for w in windows), (
        f"no one-character probe should appear here: {windows}"
    )


def test_a_kanji_that_continues_a_word_is_not_taken() -> None:
    """The 'not preceded by kana' half, on its own.

    Without it 「お茶を入れて」 would offer 茶 - which is a noun, but the rule
    cannot know that, and the same shape covers the stems this test exists to
    exclude. Pinning the boundary rather than the word list is the point.
    """

    assert "茶" not in _windows("お茶を入れて")


def test_the_rule_that_would_have_been_worse(  # noqa: D401
) -> None:
    """What a naive widening would have produced, recorded as a test.

    Measured before choosing the boundary rule: matching every lone kanji
    yields 犬・飼・方・書 for one short request. Three of those four are not
    subjects, and each would count as proof that a chunk is on topic.
    """

    windows = _windows("犬の飼い方のレポートを書いて")
    lone = [w for w in windows if len(w) == 1]

    assert lone == ["犬"], f"exactly one lone-kanji subject was named: {lone}"
