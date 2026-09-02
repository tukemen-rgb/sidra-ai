"""A generator that cannot build a genre must not answer as if it did.

The failure this guards is quiet by construction: every request produces a
page that opens and runs, so "シューティングゲームを作って" answered with a
fishing game looks like a success from every angle except the wording. These
tests pin both halves of the promise - the caveat appears when a substitution
happened, and it stays away when one did not - because a build that hedges
every answer is no more honest than one that never hedges.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import TEMPLATES, detect_genre
from sidra_ai.creation.intent import detect_creation_intent


def _outcome(tmp_path, message: str):
    generate = build_game_generator(tmp_path)
    return generate(message, detect_creation_intent(message))


def _an_unsupported_request() -> str:
    # レース left this list when its template landed; 格闘 keeps the pair of
    # tests below exercising a real gap instead of skipping.
    for text in ("シューティングゲームを作って", "パズルゲームを作って", "格闘ゲームを作って"):
        genre = detect_genre(text)
        if genre is not None and not genre.supported:
            return text
    pytest.skip("every genre in the table now has a template")


def test_a_genre_with_no_template_is_reported_as_a_substitution(tmp_path):
    message = _an_unsupported_request()
    genre = detect_genre(message)

    outcome = _outcome(tmp_path, message)

    assert genre is not None
    assert outcome.details["genre_substituted"] is True
    assert outcome.details["requested_genre"] == genre.genre
    # The operator has to be able to read both halves out of the sentence:
    # what they asked for, and what they got instead.
    assert genre.genre in outcome.summary
    built = outcome.details["built_template"]
    assert TEMPLATES[built].default_title in outcome.summary
    assert "まだ作れない" in outcome.summary


def test_a_genre_we_do_build_gets_no_apology(tmp_path):
    outcome = _outcome(tmp_path, "釣りゲームを作って")

    assert outcome.details["genre_substituted"] is False
    assert outcome.details["requested_genre"] == "釣り"
    assert "まだ作れない" not in outcome.summary


def test_a_request_that_names_no_genre_claims_no_genre(tmp_path):
    # "ゲームを作って" asks for nothing in particular, so there is nothing to
    # be wrong about - and nothing to excuse.
    outcome = _outcome(tmp_path, "ゲームを作って")

    assert detect_genre("ゲームを作って") is None
    assert outcome.details["requested_genre"] == ""
    assert outcome.details["genre_substituted"] is False
    assert "まだ作れない" not in outcome.summary


def test_the_substitution_still_hands_over_a_playable_page(tmp_path):
    # Honesty is not a consolation prize: the operator keeps the working page
    # they would have got anyway, and gains an accurate sentence about it.
    outcome = _outcome(tmp_path, _an_unsupported_request())

    assert outcome.handled is True
    assert outcome.details["playable"] is True
    assert outcome.artifact_path


def test_support_is_read_from_the_template_registry_not_a_second_list():
    # The wording has to expire on its own the day a template lands. If this
    # ever needs editing alongside TEMPLATES, the two will drift.
    for _, key, words in __import__(
        "sidra_ai.creation.games", fromlist=["_GENRES"]
    )._GENRES:
        genre = detect_genre(words[0])
        assert genre is not None
        assert genre.supported is (key in TEMPLATES)


def test_every_shipped_template_is_reachable_by_a_genre_word():
    # A template nobody can ask for by name is a template the honesty check
    # would happily substitute *away from* while the real one sat unused.
    reachable = {
        genre.template
        for words in (w for _, _, w in __import__(
            "sidra_ai.creation.games", fromlist=["_GENRES"]
        )._GENRES)
        for genre in [detect_genre(words[0])]
        if genre is not None
    }
    assert set(TEMPLATES) <= reachable
