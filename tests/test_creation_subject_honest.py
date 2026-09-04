"""The subject is named even when the title was taken away.

C-1205 taught the summary to admit that 「猫のゲームを作って」 becomes a
fishing page with no cat in it. Its test for "they named a subject" was
「the title is not the template's default」, and two things broke that:

* The trademark guard *replaces* the title with the default, so a request
  for a named work looked exactly like a request that named nothing. The
  note disappeared precisely where it was most needed - the operator asked
  for one thing, got another, and was told nothing.
* Matching a **genre** counted as satisfying the request, so 「魚の 3D
  ゲーム」 got the 3D course it asked for, containing no fish, and said so
  nowhere.

The rule is now: the subject is whatever the request called the thing once
the words naming the genre are removed. Nothing left means nothing was
promised beyond the genre, and a caveat there would be its own dishonesty.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import (  # noqa: E402
    TEMPLATES,
    choose_template,
    generate_game,
    undepicted_subject,
)
from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.router import build_default_router  # noqa: E402


def _said(request: str) -> str:
    router = build_default_router(data_dir=tempfile.mkdtemp(prefix="subject-"))
    outcome = router.route(request, detect_creation_intent(request), [])
    assert outcome.handled, request
    return outcome.summary


# ------------------------------------------------------------------ the rule


@pytest.mark.parametrize(
    "request_text", ["レースを作って", "キャッチゲームを作って", "シューティングゲームを作って"]
)
def test_a_bare_genre_leaves_no_subject(request_text: str) -> None:
    game = generate_game(request_text)

    assert not undepicted_subject(request_text, game.template, game.asked_title)


@pytest.mark.parametrize(
    "request_text,subject",
    [("猫のゲームを作って", "猫"), ("魚の 3D ゲームを作って", "魚"), ("ポケモンみたいなゲームを作って", "ポケモン")],
)
def test_a_named_subject_survives(request_text: str, subject: str) -> None:
    game = generate_game(request_text)

    assert undepicted_subject(request_text, game.template, game.asked_title) == subject


def test_the_asked_for_title_outlives_the_rename() -> None:
    """The mechanism of the bug, in one assertion."""

    game = generate_game("ポケモンみたいなゲームを作って")

    assert game.renamed is True
    assert game.title == TEMPLATES[game.template].default_title
    assert game.asked_title == "ポケモンみたいな"


# --------------------------------------------------------------- what is said


def test_a_trademarked_request_names_its_subject_and_the_rename() -> None:
    said = _said("ポケモンみたいなゲームを作って")

    assert "ポケモン" in said
    assert "作品名" in said
    # 「そのまま遊べます」 ends every summary, so match the whole clause.
    assert "のまま・難易度" not in said, "a renamed page claimed its title was kept"


def test_an_honoured_genre_still_admits_an_undepicted_subject() -> None:
    said = _said("魚の 3D ゲームを作って")

    assert "魚" in said and "絵として出てきません" in said
    assert "いちばん近い" not in said, "the genre was honoured, not substituted"


def test_a_named_work_that_is_its_genre_only_mentions_the_rename() -> None:
    """マリオ is a platformer cue, so a platformer is what was asked for.
    Nothing was dropped; only the name could not be used."""

    said = _said("マリオみたいなゲームを作って")

    assert "作品名" in said
    assert "絵として出てきません" not in said
    assert "まだ無いため" not in said


@pytest.mark.parametrize(
    "request_text", ["レースを作って", "キャッチゲームを作って", "シューティングゲームを作って"]
)
def test_a_satisfied_request_is_never_apologised_for(request_text: str) -> None:
    said = _said(request_text)

    for apology in ("絵として出てきません", "まだ無いため", "作品名"):
        assert apology not in said, said


def test_c1205s_own_case_still_holds() -> None:
    said = _said("猫のゲームを作って")

    assert "猫" in said and "まだ無いため" in said
    assert choose_template("猫のゲームを作って") == "fishing"
