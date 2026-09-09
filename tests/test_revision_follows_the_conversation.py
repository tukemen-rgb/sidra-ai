"""C-1519: 「それを難しくして」 means the thing *this* conversation is about.

Reproduced with two callers sharing one data directory - which is what a
served process is. A makes a fishing game, B makes a racing game, then A
says 「それを難しくして」 carrying A's own history. Before this change the
answer was 「レース」を修正しました: B's artifact, edited and reported back
to A under its own name. Passing no history at all gave the identical
result, which is how it was established that the reviser never read it.

``chat`` is stateless by contract - "the client replays them, which means
every turn is a claim rather than a record" - so the history is read as a
claim and used only to narrow. A conversation cannot reach an artifact it
does not name, and naming one it did not make buys nothing: typing that
name in the message already did that (C-1126).
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
    titles_in_history,
)
from sidra_ai.creation.router import build_default_router


@pytest.fixture(scope="module")
def shared() -> tuple[str, dict[str, str]]:
    """One directory, two callers - the racing game written last."""

    directory = tempfile.mkdtemp(prefix="shared-callers-")
    router = build_default_router(data_dir=directory)
    summaries: dict[str, str] = {}
    for request in ("釣りゲームを作って", "レースゲームを作って"):
        summaries[request] = router.route(
            request, detect_creation_intent(request), []
        ).summary
        # Second-resolution stamps; without this the order is not the order.
        time.sleep(1.1)
    return directory, summaries


def _history(summaries: dict[str, str], request: str) -> list[tuple[str, str]]:
    return [(request, summaries[request])]


def test_the_demonstrative_means_this_conversations_game(shared) -> None:
    directory, summaries = shared
    history = _history(summaries, "釣りゲームを作って")

    found = find_target_meta(directory, "それを難しくして", history)

    assert found is not None
    assert found[1]["title"] == "釣り", "A's demonstrative reached B's artifact"


def test_the_other_caller_still_reaches_their_own(shared) -> None:
    """The other direction: the answer follows the history it is given.

    Not, as first written here, a guard against "always pick the oldest" -
    a break test showed that claim was wrong. Once the history has narrowed
    to one candidate, every ordering rule agrees, so ordering is out of
    reach of this pair. What the pair does establish is that the target is
    a function of the history rather than a constant: swap the history and
    the answer swaps with it. Ordering is pinned separately, by the
    no-history cases below and by
    ``test_creation_revision_targeting``.
    """

    directory, summaries = shared
    history = _history(summaries, "レースゲームを作って")

    found = find_target_meta(directory, "それを難しくして", history)

    assert found is not None
    assert found[1]["title"] == "レース"


@pytest.mark.parametrize(
    "history",
    [
        # No history at all: the CLI path, unchanged.
        None,
        [],
        # A conversation that made nothing names nothing, so it narrows
        # nothing - the alternative would refuse every revision typed after
        # an ordinary question.
        [("収益化の方針は？", "掲載順は売らないことです。")],
    ],
)
def test_a_history_that_names_nothing_changes_nothing(shared, history) -> None:
    directory, _ = shared

    found = find_target_meta(directory, "それを難しくして", history)

    assert found is not None
    assert found[1]["title"] == "レース", "the latest is what a bare ask means"


def test_a_conversation_whose_game_is_gone_is_told_that(shared) -> None:
    """The third fact, and not a variant of the other two: the artifacts
    this conversation made are not on this machine. Answering with the
    titles that *are* here would be wrong and would read another caller's
    names out to this one."""

    directory, _ = shared
    history = [("将棋ゲームを作って", "「将棋」を作りました（難易度 normal）。")]
    message = "それを難しくして"

    outcome = build_game_reviser(directory)(message, detect_revision_intent(message), history)

    assert "この会話で作った「将棋」が見つかりません" in outcome.summary
    assert "レース" not in outcome.summary, "another caller's title was read out"
    assert "釣り" not in outcome.summary


def test_the_reviser_reads_the_history_it_is_given(shared) -> None:
    """End to end through the real reviser, not just the targeting rule."""

    directory, summaries = shared
    history = _history(summaries, "釣りゲームを作って")
    message = "それを紙のテーマにして"

    outcome = build_game_reviser(directory)(message, detect_revision_intent(message), history)

    assert "「釣り」を修正しました" in outcome.summary


@pytest.mark.parametrize(
    "history,want",
    [
        ([("釣りゲームを作って", "「釣り」を作りました（難易度 normal）。")], ["釣り"]),
        # A revision names it too, so a conversation that renamed its page
        # can still reach it.
        ([("タイトルを「夜」にして", "「夜」を修正しました: タイトル「夜」。")], ["夜"]),
        ([("収益化の方針は？", "掲載順は売らないことです。")], []),
        (None, []),
        ([], []),
    ],
)
def test_what_the_conversation_says_it_made(history, want) -> None:
    assert titles_in_history(history) == want


def test_the_history_cannot_reach_further_than_a_typed_name(shared) -> None:
    """The narrowing adds no reach. A history naming another caller's page
    picks the same page that typing its name already picks - so a client
    gains nothing by claiming a turn it never had."""

    directory, summaries = shared
    claimed = [("レースゲームを作って", summaries["レースゲームを作って"])]

    by_history = find_target_meta(directory, "それを難しくして", claimed)
    by_name = find_target_meta(directory, "レースのほうを難しくして")

    assert by_history is not None and by_name is not None
    assert by_history[1]["title"] == by_name[1]["title"] == "レース"


def test_the_service_hands_the_history_to_the_reviser() -> None:
    """The wire, pinned here and not only in the judge.

    A break test that removed the third argument at the call site left every
    test above green - they build the reviser directly, so they cannot see
    whether ``chat`` passes anything. This one goes through the service.
    """

    from dataclasses import replace

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    directory = tempfile.mkdtemp(prefix="service-history-")
    service = SidraService(
        settings=replace(Settings(), data_dir=directory), model=EchoModelAdapter()
    )

    made = {}
    for request in ("釣りゲームを作って", "レースゲームを作って"):
        made[request] = service.chat(request)["answer"]
        time.sleep(1.1)
    assert "「釣り」" in made["釣りゲームを作って"]
    assert "「レース」" in made["レースゲームを作って"]

    answer = service.chat(
        "それを難しくして",
        history=[("釣りゲームを作って", made["釣りゲームを作って"])],
    )["answer"]

    assert "「釣り」を修正しました" in answer
    assert "レース" not in answer, "the other caller's artifact was edited"
