"""A revision naming something that does not exist must not edit something else.

Reproduced 2026-09-09 through the real reviser: make a fishing game and a
shooter, then say 「さっきの将棋のゲームを難しくして」. No game of shogi was
ever made, and the answer came back 「『宇宙のシューティング』を修正しました:
変更なし（すでにその設定です）」 - an edit reported under a name the operator
did not say, about a game they did not mean. C-1126 matches by name, then by
genre, then falls back to the latest; the fallback fires even when the
message asserted an identity, so a wrong name is absorbed in silence.

A wrong name is information rather than noise: it usually means the operator
has lost track of what exists, and the one response that cannot help them is
quietly editing a different page. So when the message names a kind and
nothing of that kind is here, the revision refuses and says what does exist.

**This covers the genre half only.** 「将棋」 and 「猫」 name no genre at all,
so nothing in the current vocabulary can tell them from sentence glue, and
they still fall through - see the split item in `docs/BACKLOG.md`. The tests
below pin that boundary honestly rather than implying the whole defect is
closed.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.intent import detect_creation_intent  # noqa: E402
from sidra_ai.creation.revise import (  # noqa: E402
    build_game_reviser,
    detect_revision_intent,
    existing_titles,
    find_target_meta,
)
from sidra_ai.creation.router import build_default_router  # noqa: E402

MADE = ("忍者のゲームを作って", "宇宙のシューティングを作って")


@pytest.fixture(scope="module")
def made() -> str:
    directory = tempfile.mkdtemp(prefix="revision-absent-")
    router = build_default_router(data_dir=directory)
    for request in MADE:
        router.route(request, detect_creation_intent(request), [])
        time.sleep(1.1)
    return directory


@pytest.mark.parametrize(
    "message",
    [
        # A kind this project makes, but none was made here.
        "さっきのパズルのゲームを難しくして",
        "さっきのレースのゲームを難しくして",
        # A kind this project does not make at all: 落ち物パズル has no
        # template, so no artifact can ever match it.
        "テトリスのゲームを難しくして",
    ],
)
def test_a_named_kind_that_is_not_here_is_refused(made: str, message: str) -> None:
    assert find_target_meta(made, message) is None


@pytest.mark.parametrize(
    "message,want",
    [
        # The kind is named and present: unchanged behaviour.
        ("さっきのシューティングのゲームを難しくして", "shooter"),
        # Nothing named: the latest, which is what a bare ask means.
        ("さっきのを難しくして", "shooter"),
        ("それを難しくして", "shooter"),
    ],
)
def test_the_fallback_still_works_when_no_identity_was_asserted(
    made: str, message: str, want: str
) -> None:
    found = find_target_meta(made, message)
    assert found is not None, "a message that named nothing must reach the latest"
    assert found[1]["template"] == want


def test_the_refusal_says_what_does_exist(made: str) -> None:
    """A refusal that only says no leaves the operator where they started."""

    message = "テトリスのゲームを難しくして"
    revise = build_game_reviser(made)

    outcome = revise(message, detect_revision_intent(message))

    assert "見つかりません" in outcome.summary
    assert "宇宙のシューティング" in outcome.summary
    assert outcome.details["target"] == ""


def test_nothing_made_yet_keeps_its_own_wording() -> None:
    """Two different facts must not share one sentence.

    "Nothing has been made" and "what you named is not among the things that
    have been made" used to be the same refusal, which only fitted the first.
    """

    empty = tempfile.mkdtemp(prefix="revision-empty-")
    message = "テトリスのゲームを難しくして"

    outcome = build_game_reviser(empty)(message, detect_revision_intent(message))

    assert "先に" in outcome.summary and "作成してください" in outcome.summary
    assert existing_titles(empty) == []


def test_the_unfixed_half_is_recorded_rather_than_implied(made: str) -> None:
    """The boundary, pinned so it cannot be mistaken for a closed defect.

    「将棋」 names no genre, so this still lands on the latest. Asserting the
    defect keeps the split item honest: when someone fixes it, this test
    fails and points at the record instead of passing silently.
    """

    found = find_target_meta(made, "さっきの将棋のゲームを難しくして")

    assert found is not None and found[1]["template"] == "shooter", (
        "if this now refuses, the name half of C-1511 is fixed - update "
        "docs/BACKLOG.md and delete this test"
    )


@pytest.mark.parametrize(
    "message",
    [
        # The genre word is inside the *new* name, not a statement about
        # which page is meant. This one was not in the battery of phrasings
        # written for the fix; the existing suite caught it
        # (test_title_revision_still_passes_the_trademark_guard) after the
        # refusal had already been measured as "0 false refusals in 20".
        "ゲームのタイトルを「ゼルダの冒険」にして",
        "さっきのタイトルを「レースの王」に変えて",
        "タイトルを「パズルの塔」にして",
    ],
)
def test_a_genre_word_inside_a_new_title_is_not_a_target(
    made: str, message: str
) -> None:
    found = find_target_meta(made, message)

    assert found is not None, (
        "renaming a page must not be read as naming a different page"
    )
