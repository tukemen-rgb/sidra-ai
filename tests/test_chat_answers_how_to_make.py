"""C-1875: 「レポートの作り方を教えて」 must not reach the index wall.

「使い方を教えて」 is answered from the live generator registry (C-1802). The
same question about the same product, phrased with a subject, was not:
`_HELP_QUERIES` matches whole messages, so 「レポートの作り方を教えて」 fell
through to retrieval and got the abstention that asks an administrator to
ingest a repository. Measured on the real `chat` before the fix, four
phrasings hit that wall.

The tests that matter most here are the ones in the other direction. A branch
that answered everything with the product's menu would satisfy the first half
and wreck the product.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import _how_to_make_kinds
from sidra_ai.evals.chat_answers_how_to_make import (
    evaluate_chat_answers_how_to_make,
)

_KINDS = ("art", "deck", "document", "game", "gif", "model3d", "project")


@pytest.mark.parametrize(
    "message,expected",
    [
        ("レポートの作り方を教えて", "document"),
        ("ゲームの作り方を教えて", "game"),
        ("スライドの作り方を教えて", "deck"),
        # The subject sits between the question word and the verb - how people
        # actually ask, and what a contiguous 「どうやって作」 cue missed.
        ("どうやってレポートを作るの", "document"),
        ("どのようにスライドを作りますか", "deck"),
        ("ゲームを作るには", "game"),
    ],
)
def test_a_how_to_question_names_the_kind_it_is_about(message, expected) -> None:
    assert expected in _how_to_make_kinds(message, _KINDS)


@pytest.mark.parametrize(
    "message,why",
    [
        ("カレーの作り方を教えて", "the product does not make curry"),
        ("レポートの作り方をドキュメントから探して", "names a source: a corpus question"),
        ("ゲームの作り方をリポジトリから探して", "names a source: a corpus question"),
        ("作り方を教えて", "names nothing, so it could be about the corpus"),
        ("レースゲームを作って", "this is a request to make one, not a question"),
        ("犬のレポートを作って", "this is a request to make one, not a question"),
        ("収益化の方針を教えて", "an ordinary corpus question"),
    ],
)
def test_what_the_branch_must_not_swallow(message, why) -> None:
    assert _how_to_make_kinds(message, _KINDS) == (), why


def test_the_vocabulary_follows_the_registry_not_a_second_list() -> None:
    """A kind the router does not register cannot be matched.

    The labels come from `registered_kinds` through `_KIND_LABELS`, so adding
    or dropping a generator moves this with no edit here. Passing a narrowed
    registry is how that is checked from outside.
    """

    assert _how_to_make_kinds("ゲームの作り方を教えて", ("document",)) == ()
    assert _how_to_make_kinds("ゲームの作り方を教えて", ("game",)) == ("game",)


def test_the_judge_agrees_and_says_so() -> None:
    result = evaluate_chat_answers_how_to_make()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
