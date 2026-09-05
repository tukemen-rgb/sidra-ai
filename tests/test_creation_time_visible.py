"""C-1417: the last ten seconds, said out loud.

The shared clock has always ended a go at sixty seconds, and nothing on the
screen ever mentioned it - so 「ここまで」 arrived out of nowhere. §8 事実 1
asks for a break inside about a minute, and a break you cannot see coming is
a surprise rather than a break.

Two things are deliberately *not* done here, and both have tests: the
countdown does not run for the whole minute (条件①, because a clock over the
whole go turns 「気楽な 1 分」 into an exam), and it is not silenced by
reduced motion (条件②, because it is a number rather than a movement).

It also declines to answer E 節's open question (C-1127, whether the buzzer
is a break or a defeat): 「のこり」 says time is passing, not that anybody
is losing.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game, select_theme
from sidra_ai.creation.round import (
    ROUND_CLOCK_BOX,
    ROUND_SECONDS,
    ROUND_SHOW_MS,
    ROUND_URGENT_MS,
    clock_probe_source,
)

#: catch has no ending of its own, so an unattended go runs to the buzzer -
#: which is the only situation the countdown exists for.
TEMPLATE = "catch"


def _play(**kwargs) -> list[dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play a whole round")
    page = generate_game("ゲームを作って", template=TEMPLATE).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=clock_probe_source(script.group(1), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])["frames"]


@pytest.fixture(scope="module")
def frames() -> list[dict]:
    return _play()


def _late(frames: list[dict]) -> list[dict]:
    return [f for f in frames if f["ms"] < ROUND_SHOW_MS and not f["done"]]


# --- the shape of the rule -------------------------------------------------


def test_the_window_is_a_tenth_of_the_go() -> None:
    assert ROUND_SHOW_MS < ROUND_SECONDS * 1000
    assert ROUND_URGENT_MS < ROUND_SHOW_MS


def test_the_badge_sits_below_the_hud_row() -> None:
    # Chosen by measurement: every template was driven and its paint
    # recorded, and this band is the only one carrying no text in any of
    # the ten. The corners are all spoken for - seven templates print their
    # score at the top left, two at the top right, three at the bottom
    # left, and the on-screen pad owns the bottom right on a phone.
    _, top, _, height = ROUND_CLOCK_BOX
    assert top >= 44, "the HUD row is above this"
    assert top + height <= 92


# --- what a whole go looks like --------------------------------------------


def test_nothing_about_time_for_the_first_fifty_seconds(frames: list[dict]) -> None:
    early = [f for f in frames if f["ms"] >= ROUND_SHOW_MS]
    assert early, "the go never even started"
    assert not [f for f in early if f["said"]]
    assert not [f for f in early if f["due"]]


def test_every_redrawn_frame_after_that_says_so(frames: list[dict]) -> None:
    late = _late(frames)
    assert late, "the go did not reach the last ten seconds"
    # "Redrawn" is the qualifier. The juice kit freezes the loop for a few
    # frames on a hit, and those frames paint nothing at all - the canvas
    # keeps the previous picture, badge included. A frame that redrew the
    # game and left the badge off it would be a real flicker.
    assert not [f for f in late if f["all"] and not f["said"]]


def test_the_number_is_the_clock_behind_it(frames: list[dict]) -> None:
    for frame in _late(frames):
        if frame["said"]:
            assert frame["said"] == f"のこり {math.ceil(frame['ms'] / 1000)}"


def test_the_last_seconds_are_marked_and_the_earlier_ones_are_not(
    frames: list[dict],
) -> None:
    tokens = select_theme("ゲームを作って").tokens
    late = [f for f in _late(frames) if f["said"]]
    assert {f["ink"] for f in late if f["ms"] <= ROUND_URGENT_MS} == {tokens["alert"]}
    assert {f["ink"] for f in late if f["ms"] > ROUND_URGENT_MS} == {tokens["text"]}


def test_the_countdown_does_not_outlive_the_round(frames: list[dict]) -> None:
    assert not [f for f in frames if f["done"] and f["said"]]


def test_reduced_motion_still_gets_the_number() -> None:
    # §1's particles and §16's haptics are decorations and go quiet. This
    # is a fact about the round, and facts do not.
    quiet = _play(reduced=True)
    assert len([f for f in quiet if f["said"]]) == len([f for f in _play() if f["said"]])
    assert [f for f in quiet if f["said"]]


def test_the_wording_does_not_call_it_a_defeat() -> None:
    # E 節 C-1127 is still open on whether the buzzer is a break or a loss.
    # This says neither.
    said = {f["said"] for f in _late(_play()) if f["said"]}
    assert said
    for line in said:
        assert line.startswith("のこり ")
        assert not any(word in line for word in ("負け", "失敗", "ゲームオーバー"))
