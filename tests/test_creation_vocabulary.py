"""One list of what a game request can name, for everyone who asks.

C-1120: the genre table lived in ``games.py`` and ``intent.py`` kept a
third, hand-written list of game words. They drifted, and the drift showed
at the front door - 「レースを作って」 was not even read as a creation
request, so it got retrieval boilerplate, while ``choose_template`` knew
perfectly well to build a race.

The tests here pin the property that makes that impossible to repeat: the
detector's vocabulary is *derived* from the routing table, and the routing
table's words are the template modules' own. Anything routable is
recognised, by construction rather than by remembering to update a list.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, choose_template, detect_genre  # noqa: E402
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.router import build_default_router  # noqa: E402
from sidra_ai.creation.vocabulary import (  # noqa: E402
    GAME_WORDS,
    GENERIC_GAME_WORDS,
    GENRES,
    labels_for,
)

#: The eight the self-test found turned away at the front door.
FOUND_BY_THE_SELF_TEST = (
    ("横スクロールのジャンプアクションを作って", "platformer"),
    ("レースを作って", "racing"),
    ("ぷよぷよみたいなの作って", "puzzle"),
    ("さめがめを作って", "puzzle"),
    ("テトリスみたいなゲームを作って", None),
    ("RPG を作って", None),
    ("音ゲーを作って", None),
    ("タワーディフェンスを作って", None),
)


# ------------------------------------------------- the property, not the list


def test_every_word_that_routes_is_a_word_that_is_recognised() -> None:
    """The defect, stated as an invariant.

    A genre cannot be routable and unrecognised at the same time, because
    the detector's list is built from the routing table rather than kept
    beside it.
    """

    for _label, _template, words in GENRES:
        for word in words:
            assert word in GAME_WORDS, word


def test_the_generic_words_survive_too() -> None:
    for word in GENERIC_GAME_WORDS:
        assert word in GAME_WORDS


def test_the_table_still_names_genres_we_cannot_build() -> None:
    """Not an oversight: naming them is what lets one be declined in the
    asker's own words instead of silently becoming a fishing game."""

    unbuildable = [label for label, template, _ in GENRES if template not in TEMPLATES]

    assert unbuildable, "nothing can be declined by name any more"
    assert "RPG" in unbuildable


@pytest.mark.parametrize("text,template", FOUND_BY_THE_SELF_TEST)
def test_the_front_door_lets_them_in(text: str, template: str | None) -> None:
    assert detect_creation_intent(text).kind.value == "game", text
    if template is not None:
        assert choose_template(text) == template


@pytest.mark.parametrize("text,template", FOUND_BY_THE_SELF_TEST)
def test_the_unbuildable_ones_are_marked_as_such(text: str, template: str | None) -> None:
    genre = detect_genre(text)

    assert genre is not None, text
    assert genre.supported is (template is not None)


# --------------------------------------------------------------- what it says


def _summary(text: str) -> str:
    router = build_default_router(data_dir=tempfile.mkdtemp(prefix="vocab-"))
    outcome = router.route(text, detect_creation_intent(text), [])
    assert outcome.handled, text
    return outcome.summary


def test_a_decline_names_the_genre_that_was_asked_for() -> None:
    assert "RPG" in _summary("RPG を作って")


def test_a_decline_lists_what_can_actually_be_built() -> None:
    """Calling a fishing page "the nearest thing to an RPG" is true only in
    the sense that it was the fallback."""

    said = _summary("RPG を作って")

    for label in labels_for(TEMPLATES):
        assert label in said, label


def test_a_decline_never_offers_a_genre_that_does_not_exist() -> None:
    said = _summary("RPG を作って")
    phantom = [
        label
        for label, template, _ in GENRES
        if template not in TEMPLATES and label != "RPG"
    ]

    assert phantom, "the fixture needs at least one other unbuildable genre"
    for label in phantom:
        assert label not in said, label


def test_a_request_we_can_honour_carries_no_apology() -> None:
    """A caveat on a request we did satisfy is its own dishonesty."""

    said = _summary("レースを作って")

    assert "まだ作れない" not in said
    assert "いま作れるのは" not in said
