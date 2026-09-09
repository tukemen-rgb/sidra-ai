"""C-1513: two ways of pointing at what already exists that the product
promised and did not accept.

**「〜のやつ」.** 「忍者のやつを紙のテーマにして」 points at a page as plainly
as 「それ」 does. It was declined - not because the sentence was unclear,
but because やつ was in no table, so 「さっきのやつ」 worked (さっき carried
the reference) and 「忍者のやつ」 did not.

**「元に戻して」.** Every revision signs off with 「旧版のファイルもそのまま
残っています」. Until now no sentence reached those files, so the product
was advertising a history nobody could walk.

The second half is the one that needs watching. Making やつ a referent also
made 「将棋のやつを難しくして」 reach the targeting rules, where - measured,
not assumed - it silently edited the newest page: the exact failure C-1511b
had just closed for 「〜のゲーム」. That is why やつ is a trigger there too.
"""

from __future__ import annotations

import tempfile
import time

import pytest

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.revise import (
    build_game_reviser,
    detect_revision_intent,
    find_target_meta,
)
from sidra_ai.creation.router import build_default_router


def _make(*requests: str) -> str:
    directory = tempfile.mkdtemp(prefix="undo-")
    router = build_default_router(data_dir=directory)
    for request in requests:
        router.route(request, detect_creation_intent(request), [])
        # Second-resolution stamps; without this the order is not the order.
        time.sleep(1.1)
    return directory


@pytest.fixture(scope="module")
def made() -> str:
    return _make("忍者のゲームを作って", "宇宙のシューティングを作って")


# --------------------------------------------------------------- 「〜のやつ」


@pytest.mark.parametrize(
    "message,adjustment",
    [
        ("忍者のやつを紙のテーマにして", "theme"),
        ("そのやつを難しくして", "difficulty"),
        ("さっきのやつを赤にして", "accent"),
    ],
)
def test_that_one_points_at_a_page(message: str, adjustment: str) -> None:
    intent = detect_revision_intent(message)
    assert intent.is_revision is True
    assert adjustment in intent.adjustments


@pytest.mark.parametrize(
    "message",
    [
        # The creation detector still owns a make verb.
        "面白いやつを作って",
        # A question is still a question.
        "そのやつは何ですか",
        # A referent with nothing recognisable to change is still declined.
        "そのやつをどうにかして",
    ],
)
def test_that_one_does_not_swallow_the_vetoes(message: str) -> None:
    assert detect_revision_intent(message).is_revision is False


@pytest.mark.parametrize(
    "message",
    ["将棋のやつを難しくして", "猫のやつを赤にして"],
)
def test_a_named_that_one_that_is_not_here_is_not_edited_quietly(
    made: str, message: str
) -> None:
    """The hole this change opened, closed in the same change.

    Before やつ was a referent these never reached the targeting rules at
    all. Measured after making it one: both landed on the newest page and
    reported success under its name.
    """

    assert find_target_meta(made, message) is None


@pytest.mark.parametrize(
    "message,want",
    [
        ("忍者のやつを難しくして", "忍者"),
        ("シューティングのやつを難しくして", "宇宙のシューティング"),
        ("さっきのやつを難しくして", "宇宙のシューティング"),
        ("そのやつを難しくして", "宇宙のシューティング"),
        ("前のやつを難しくして", "宇宙のシューティング"),
        ("最新のやつを難しくして", "宇宙のシューティング"),
    ],
)
def test_that_one_still_lands_where_it_should(made: str, message: str, want: str) -> None:
    found = find_target_meta(made, message)
    assert found is not None, f"{message} lost its target"
    assert found[1]["title"] == want


# ------------------------------------------------------------- 「元に戻して」


@pytest.mark.parametrize(
    "message",
    [
        "さっきの変更を元に戻して",
        "さっきのを元に戻して",
        "そのゲームを元通りにして",
        "さっきの修正を取り消して",
    ],
)
def test_undo_is_an_instruction(message: str) -> None:
    intent = detect_revision_intent(message)
    assert intent.is_revision is True
    assert intent.adjustments == {"revert": "1"}


def test_undo_restores_the_parameters_of_the_previous_version() -> None:
    directory = _make("忍者のゲームを作って")
    revise = build_game_reviser(directory)

    harder = "さっきのゲームを難しくして"
    revise(harder, detect_revision_intent(harder))
    time.sleep(1.1)
    assert find_target_meta(directory, "難しくして")[1]["difficulty"] == "hard"

    undo = "さっきの変更を元に戻して"
    outcome = revise(undo, detect_revision_intent(undo))

    assert "一つ前の版に戻しました" in outcome.summary
    assert "難易度 hard→normal" in outcome.summary
    assert find_target_meta(directory, "難しくして")[1]["difficulty"] == "normal"


def test_undo_leaves_the_version_it_left_behind_on_disk() -> None:
    """Undo is not a delete. The sign-off promises the older files are
    still there, and the sentence that reaches them must not be the one
    that removes them."""

    directory = _make("忍者のゲームを作って")
    revise = build_game_reviser(directory)
    for message in ("さっきのゲームを難しくして", "さっきの変更を元に戻して"):
        revise(message, detect_revision_intent(message))
        time.sleep(1.1)

    from pathlib import Path

    metas = sorted((Path(directory) / "artifacts").glob("game-*.meta.json"))
    assert len(metas) == 3, "the version being left behind was not kept"


def test_undo_with_no_history_says_so_rather_than_doing_nothing() -> None:
    directory = _make("猫のゲームを作って")
    message = "さっきのゲームを元に戻して"

    outcome = build_game_reviser(directory)(message, detect_revision_intent(message))

    assert "戻せる前の版がありません" in outcome.summary
    assert "修正しました" not in outcome.summary


def test_a_named_change_still_wins_over_the_undo_idiom() -> None:
    """「タイトルを元に戻して」 is a rename to 「元」 today. Undo speaks only
    when the message named no change of its own, so that meaning is
    unchanged - the conservative half of a genuine ambiguity."""

    intent = detect_revision_intent("さっきのゲームのタイトルを元に戻して")

    assert intent.adjustments == {"title": "元"}
    assert "revert" not in intent.adjustments


def test_bare_undo_without_a_referent_is_still_declined() -> None:
    """Measured and deliberately left alone: 「元に戻して」 on its own carries
    no back-reference, exactly like a bare 「難しくして」, and making the undo
    idiom its own referent would put every 「設定を元に戻してください」 into
    the reviser. Recorded in the backlog instead of guessed at here."""

    assert detect_revision_intent("元に戻して").is_revision is False
