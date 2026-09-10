"""C-1516: the English title was the whole request.

Japanese puts the making verb at the end, so one trailing pattern took it
off and 「レースゲームを作って」 became 「レース」. English puts it at the
front, nothing took it off, and ``make me a racing game`` was the page's own
title - heading included.

A longer English request ("please make a racing game", 25 characters) ran
past the 24-character limit and fell back to the *Japanese* default title,
so an English request came back named 「タイミング釣り」. That second symptom
was found while measuring the first.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import _title_from

FALLBACK = "タイミング釣り"


@pytest.mark.parametrize(
    "request_text,want",
    [
        ("make me a racing game", "racing"),
        ("Create a puzzle game", "puzzle"),
        ("build a shooting game", "shooting"),
        ("generate a maze game", "maze"),
        ("please make a racing game", "racing"),
        ("can you make me a racing game", "racing"),
    ],
)
def test_the_english_making_verb_is_not_part_of_the_name(request_text, want) -> None:
    assert _title_from(request_text, FALLBACK) == want


def test_a_long_english_request_no_longer_answers_in_japanese() -> None:
    """The second symptom: 25 characters overran the limit, and the fallback
    is a Japanese title."""

    assert len("please make a racing game") > 24
    assert _title_from("please make a racing game", FALLBACK) != FALLBACK


@pytest.mark.parametrize(
    "request_text,want",
    [
        ("レースゲームを作って", "レース"),
        ("パズルゲームを作って", "パズル"),
        ("猫のゲームを作って", "猫"),
    ],
)
def test_japanese_still_drops_its_own_verb(request_text, want) -> None:
    """A shared helper is where a fix for one language breaks the other."""

    assert _title_from(request_text, FALLBACK) == want


@pytest.mark.parametrize(
    "request_text",
    [
        # No verb: every word the operator used is kept, in either language.
        # Removing the trailing "game" unconditionally would be a wider rule
        # than the Japanese one, which needs the verb before it strips.
        "racing game",
        "a racing game",
        "レースゲーム",
        "cats",
    ],
)
def test_a_request_without_a_making_verb_keeps_its_words(request_text: str) -> None:
    assert _title_from(request_text, FALLBACK) == request_text


def test_a_request_that_is_only_the_verb_falls_back() -> None:
    """Stripping everything must not leave an empty title.

    C-1526 changed what it falls back *to*. Keeping the raw 「make a game」
    was the guard C-1516 reached for, and it made the page title itself
    the subject: the honesty note then said 「「make a game」は絵として出て
    きません」 about a request that named no subject at all. The template's
    own default is where the Japanese 「ゲームを作って」 has always landed,
    and the note is silent there for the right reason - nothing was
    promised beyond the artifact.
    """

    assert _title_from("make a game", FALLBACK) == FALLBACK
    assert _title_from("create an app", FALLBACK) == FALLBACK
