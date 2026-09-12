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


@pytest.mark.parametrize(
    "request_text,want",
    [
        # C-1531: English can put the request marker at the *end*, where the
        # head pattern above never looks. 「a racing game, please」 carries no
        # making verb at all and titled the page with all four of its words.
        ("a racing game, please", "racing"),
        ("a racing game please", "racing"),
        ("racing game please", "racing"),
        ("puzzle please", "puzzle"),
        ("puzzle pls", "puzzle"),
        # And the give-imperative the head list never knew. The router
        # accepted these the day before (C-1530); the title builder did not,
        # which is the third time widening the door left this rule behind.
        ("gimme a racing game", "racing"),
        ("give me a racing game", "racing"),
    ],
)
def test_an_english_request_marker_at_the_end_is_not_part_of_the_name(
    request_text: str, want: str
) -> None:
    assert _title_from(request_text, FALLBACK) == want


def test_the_english_marker_is_the_japanese_rule_in_the_other_language() -> None:
    """Written as a pair, because the claim is that these two behave alike.

    C-1529 made 「ください」 a request marker on the Japanese side, so
    「パズルをください」 titles itself 「パズル」. 「a racing game, please」 is
    that sentence in English and was keeping every word. Asserting both here
    means the English side cannot be "fixed" by a rule that quietly drifts
    away from the Japanese one.
    """

    assert _title_from("パズルをください", FALLBACK) == "パズル"
    assert _title_from("a puzzle game, please", FALLBACK) == "puzzle"


def test_the_marker_is_what_makes_the_article_strippable() -> None:
    """The C-1528 pin, stated as the contrast it actually is.

    Making the bare article a request head was tried and the judge refused
    it. So the article comes off only once a marker has said this is a
    request - which is exactly what separates 「レースゲーム」 from
    「レースゲームをください」.
    """

    assert _title_from("a racing game", FALLBACK) == "a racing game"
    assert _title_from("a racing game, please", FALLBACK) == "racing"
    assert _title_from("レースゲーム", FALLBACK) == "レースゲーム"
    assert _title_from("レースゲームをください", FALLBACK) == "レース"


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
