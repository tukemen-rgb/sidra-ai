"""C-1511b: a message that says which game it means, in words no genre
table knows.

C-1511 stopped 「テトリスのゲームを難しくして」 from silently editing whatever
was newest, but only because テトリス is a word ``detect_genre`` recognises.
「さっきの将棋のゲームを難しくして」 asserts an identity exactly as plainly and
was indistinguishable from sentence glue, so it kept landing on the latest
page and reporting success under *that* page's name.

Both directions are checked here, and the second half is the one that
matters: a reviser that refuses everything would pass the first half
outright. The pointer phrasings (「前のゲーム」「今のゲーム」) are shipped ones
- they are pinned by ``test_revision_demonstrative_referent`` and
``test_revision_polite_request_is_revision`` - and they are here because
over-refusing them is the failure this fix was warned about when it was
split out.
"""

from __future__ import annotations

import tempfile
import time

import pytest

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.revise import (
    _asserted_subject,
    build_game_reviser,
    detect_revision_intent,
    find_target_meta,
)
from sidra_ai.creation.router import build_default_router

#: A named page and a genre page, in that order, so "latest" is the shooter
#: and every wrong answer is the same wrong answer.
MADE = ("忍者のゲームを作って", "宇宙のシューティングを作って")


@pytest.fixture(scope="module")
def made() -> str:
    directory = tempfile.mkdtemp(prefix="named-subject-")
    router = build_default_router(data_dir=directory)
    for request in MADE:
        router.route(request, detect_creation_intent(request), [])
        # Second-resolution stamps; without this the order is not the order.
        time.sleep(1.1)
    return directory


@pytest.mark.parametrize(
    "message",
    [
        "さっきの将棋のゲームを難しくして",
        "猫のゲームを難しくして",
        "将棋のゲームをやさしくして",
        "チェスのゲームを赤にして",
    ],
)
def test_a_game_that_is_not_here_is_not_edited_quietly(made: str, message: str) -> None:
    assert find_target_meta(made, message) is None


def test_the_refusal_says_what_does_exist(made: str) -> None:
    """Naming what is here is the difference between a refusal that helps
    and one that only says no - the operator usually mistyped, and the one
    thing that cannot help them is editing something else."""

    message = "さっきの将棋のゲームを難しくして"
    outcome = build_game_reviser(made)(message, detect_revision_intent(message))
    assert outcome.handled is True
    assert "見つかりません" in outcome.summary
    assert "宇宙のシューティング" in outcome.summary
    assert "将棋" not in outcome.summary


@pytest.mark.parametrize(
    "message,want",
    [
        # The page really is here, named: unchanged.
        ("忍者のゲームを難しくして", "忍者"),
        # The genre rule still owns the words it knows.
        ("さっきのシューティングのゲームを難しくして", "宇宙のシューティング"),
        # Nothing named at all: the latest, which is what a bare ask means.
        ("さっきのゲームを難しくして", "宇宙のシューティング"),
        ("それを難しくして", "宇宙のシューティング"),
        ("難しくして", "宇宙のシューティング"),
        # Pointer words say *which one*, not *what about*. Refusing these
        # would break requests that land correctly today.
        ("前のゲームを簡単にして", "宇宙のシューティング"),
        ("今のゲームを紙の配色にしてもらえますか", "宇宙のシューティング"),
        ("この前のゲームを難しくして", "宇宙のシューティング"),
        ("昨日のゲームを難しくして", "宇宙のシューティング"),
        ("今日のゲームを難しくして", "宇宙のシューティング"),
        ("最新のゲームを難しくして", "宇宙のシューティング"),
        ("最後のゲームを難しくして", "宇宙のシューティング"),
        ("最初のゲームを難しくして", "宇宙のシューティング"),
        ("別のゲームを難しくして", "宇宙のシューティング"),
        # A subject inside a *new* title is not a statement about which
        # page is meant - this renames the shooter, it does not ask for a
        # cat game. Measured to match here before the title was stripped.
        ("さっきのゲームのタイトルを「猫のゲーム」にして", "宇宙のシューティング"),
    ],
)
def test_the_revision_still_lands_where_it_did(made: str, message: str, want: str) -> None:
    found = find_target_meta(made, message)
    assert found is not None, f"{message} lost its target"
    assert found[1]["title"] == want


@pytest.mark.parametrize(
    "message,want",
    [
        ("さっきの将棋のゲームを難しくして", "将棋"),
        ("猫のゲームを難しくして", "猫"),
        ("RPGのゲームを難しくして", "RPG"),
        # Nothing asserted: no subject, so nothing to refuse on.
        ("さっきのゲームを難しくして", ""),
        ("前のゲームを簡単にして", ""),
        ("元のゲームに戻して", ""),
        # 「ほう」/「やつ」 are deliberately not triggers: the split warned
        # these would over-refuse, and measuring first showed neither is a
        # revision at all - so the rule does not need to know about them.
        ("色のほうを変えて", ""),
        ("難易度のほうを上げて", ""),
    ],
)
def test_what_the_message_says_it_is_about(message: str, want: str) -> None:
    assert _asserted_subject(message) == want


@pytest.mark.parametrize("message", ["色のほうを変えて", "難易度のほうを上げて", "敵を増やして"])
def test_the_phrasings_the_split_warned_about_were_never_revisions(message: str) -> None:
    """Measured before the fix, and recorded because it corrects the
    filing: 「色のほう」 and 「難易度のほう」 never reached the target rule at
    all - without a referent they are not evidence a game is meant."""

    assert detect_revision_intent(message).is_revision is False
