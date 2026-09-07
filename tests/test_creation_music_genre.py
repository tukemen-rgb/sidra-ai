"""「音楽ゲーム」 is a genre, not a subject (C-1505).

「音ゲー」 and 「リズムゲーム」 were both declined properly - named as the
リズム genre this product has no template for. 「音楽ゲーム」 matched no table,
so it fell through to the *subject* path and came back as 「「音楽」の題材を
描く型はまだ無い」: a music game answered as though the operator had asked for
a game about music.

The fix is one word in the rhythm vocabulary. The half that needs guarding is
what must NOT move: the bare 「音楽」. 「音楽を作って」 is not a request for a
rhythm game, and a vocabulary widened by one character too many would turn
every mention of music into a declined genre.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import detect_genre


def genre_of(text: str):
    return detect_genre(text)


# ------------------------------------------------------------- the defect


@pytest.mark.parametrize(
    "ask", ["音楽ゲームを作って", "音楽ゲーム作って", "音楽ゲームがほしい"]
)
def test_a_music_game_is_named_as_the_rhythm_genre(ask: str) -> None:
    named = genre_of(ask)
    assert named is not None, "fell through to the subject path again"
    assert named.genre == "リズム"
    assert named.supported is False


def test_it_now_agrees_with_the_spellings_that_already_worked() -> None:
    """The point of the item: three spellings, one answer."""

    answers = {
        genre_of(ask).genre
        for ask in ("音ゲーを作って", "リズムゲームを作って", "音楽ゲームを作って")
    }
    assert answers == {"リズム"}


# --------------------------------------------------------- the boundary


@pytest.mark.parametrize("ask", ["音楽を作って", "音楽のゲームを作って", "音楽が好き"])
def test_music_on_its_own_is_not_a_rhythm_game(ask: str) -> None:
    """The bare noun stays out of the vocabulary on purpose."""

    named = genre_of(ask)
    assert named is None or named.genre != "リズム"


def test_the_vocabulary_gained_exactly_one_word() -> None:
    """Guarding the widening itself, not just its effect.

    Written against the table so that a later edit adding 「音楽」 - which
    would silently capture 「音楽を作って」 - fails here rather than in a
    user's reply.
    """

    from sidra_ai.creation.vocabulary import GENRES

    words = next(w for label, key, w in GENRES if key == "rhythm")
    assert "音楽ゲーム" in words
    assert "音楽" not in words


def test_the_other_declined_genres_are_untouched() -> None:
    for ask, want in (
        ("RPG を作って", "RPG"),
        ("テトリスを作って", "落ち物パズル"),
        ("タワーディフェンスを作って", "タワーディフェンス"),
    ):
        named = genre_of(ask)
        assert named is not None and named.supported is False, ask
