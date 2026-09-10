"""C-1526: 「game」 is not what the game is about.

`chat("create a fishing game please")` answered 「『タイミング釣り』型で
作りました。ただし「game」は絵として出てきません」 - the honesty note
naming the word for *the artifact* as the subject the page failed to draw.
「make a game」 was worse: with nothing left after the verb, the guard kept
the whole request as the title, so the page said 「make a game」 is not
drawn.

The filing said Japanese already had a list for this and only English
lacked one. Half right: 「レースのアプリを作って」 came back as 「「アプリ」
は絵として出てきません」 too, so Japanese needed the removal as well - but
only in that shape. A bare 「アプリを作って」 (and 「create an app」) never
reaches a generator at all; the router calls it UNKNOWN, and the first
version of this file asserted things about it through ``generate_game``,
which is not a path any operator can take. The judge caught that before
it was merged.

An artifact noun is kept apart from a genre word on purpose. A genre word
is trimmed because the page *delivered* that genre; an artifact noun is
trimmed because it never named a subject at all. Merging the two would
strip 「dragon」 out of 「a game about a dragon」 - a subject the page really
cannot draw - because DUEL_WORDS carries 「dragon ball」.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import (
    TEMPLATES,
    _title_from,
    choose_template,
    generate_game,
    undepicted_subject,
)
from sidra_ai.creation.vocabulary import ARTIFACT_NOUNS, GENERIC_GAME_WORDS


def _subject(request: str) -> str:
    game = generate_game(request)
    return undepicted_subject(request, game.template, game.asked_title)


# --- the artifact noun is never the subject --------------------------


@pytest.mark.parametrize(
    "request_text",
    [
        # The filing's own repro.
        "create a fishing game please",
        "make me a racing game",
        "build a puzzle game",
        # Nothing but the artifact: the English 「ゲームを作って」.
        "make a game",
        "make a racing app",
        # ...and the same in Japanese, which the filing believed was fine.
        "レースのアプリを作って",
        "ゲームを作って",
    ],
)
def test_no_caveat_names_the_thing_that_was_made(request_text: str) -> None:
    assert _subject(request_text) == ""


@pytest.mark.parametrize("request_text", ["アプリを作って", "create an app", "猫のアプリを作って"])
def test_a_bare_app_request_never_reaches_a_generator(request_text: str) -> None:
    """Recorded because this file first claimed otherwise.

    ``generate_game`` will happily build a page for any string, so calling
    it directly made 「アプリを作って」 look like a live defect. The router
    is what an operator goes through, and it classes these UNKNOWN - no
    game, no summary, no caveat. The artifact noun only reaches the game
    path with a genre word beside it, which is why the list above stops at
    「レースのアプリを作って」.
    """

    from sidra_ai.creation.intent import CreationKind, detect_creation_intent

    assert detect_creation_intent(request_text).kind is CreationKind.UNKNOWN


@pytest.mark.parametrize(
    "request_text,want",
    [
        # Both directions: a real subject beside the artifact noun still
        # gets named, or this metric is passed by deleting the note.
        ("make a cat game", "cat"),
        ("create a game about a dog", "dog"),
        ("make a game about space", "space"),
        ("猫のゲームを作って", "猫"),
    ],
)
def test_a_real_subject_beside_it_is_still_named(request_text: str, want: str) -> None:
    assert _subject(request_text) == want


# --- and the title stops being the request ---------------------------


def test_a_request_with_nothing_but_the_artifact_takes_the_default_title() -> None:
    """Keeping the raw request was what put 「make a game」 in the caveat."""

    fallback = TEMPLATES["fishing"].default_title

    assert _title_from("make a game", fallback) == fallback
    # 「create an app」 never reaches a generator (see the UNKNOWN test
    # above), but the stripper is shared and must not leave it empty.
    assert _title_from("create an app", fallback) == fallback


def test_stacked_tail_words_all_come_off() -> None:
    """「fishing game please」 has two, and one pass left 「fishing game」."""

    fallback = TEMPLATES["fishing"].default_title

    assert _title_from("create a fishing game please", fallback) == "fishing"
    assert _title_from("build a puzzle game thanks", fallback) == "puzzle"


def test_a_request_without_a_making_verb_is_left_alone() -> None:
    """C-1516's rule, unchanged: no verb, no stripping. Otherwise a title
    the operator typed outright would be edited."""

    fallback = TEMPLATES["fishing"].default_title

    assert _title_from("racing game", fallback) == "racing game"
    assert _title_from("レースゲーム", fallback) == "レースゲーム"


# --- where the list comes from ---------------------------------------


def test_the_two_lists_are_not_the_same_question() -> None:
    """A named work is a game request and a *subject*; splitting them is
    the whole reason ARTIFACT_NOUNS exists as its own name."""

    assert "ゼルダ" in GENERIC_GAME_WORDS
    assert "ゼルダ" not in ARTIFACT_NOUNS
    assert "ドラゴンボール" not in ARTIFACT_NOUNS
    # ...and the overlap is shared, not copied, so the two cannot drift.
    for word in ("ゲーム", "game", "minigame"):
        assert word in GENERIC_GAME_WORDS
        assert word in ARTIFACT_NOUNS


def test_a_genre_word_is_not_swept_up_with_the_artifact_nouns() -> None:
    """The failure the split exists to prevent: 「dragon」 reaches
    ARTIFACT_NOUNS only through DUEL_WORDS, and stripping it would silence
    a subject the page really cannot draw."""

    assert "dragon" not in ARTIFACT_NOUNS
    assert _subject("create a game about a dragon") == "dragon"


def test_the_english_tail_is_built_from_the_list() -> None:
    """Not hand-written beside it: adding an artifact noun has to reach the
    title stripper without a second edit."""

    from sidra_ai.creation.games import _STRIP_EN_TAIL

    for word in ARTIFACT_NOUNS:
        if word.isascii():
            assert _STRIP_EN_TAIL.search(f" {word}"), word


def test_the_router_still_reads_these_as_game_requests() -> None:
    """Splitting the list must not change what routes where."""

    for request in ("make a game", "ゲームを作って", "make a racing app", "レースのアプリを作って"):
        assert choose_template(request) in TEMPLATES
