"""The whole creature is a moment, not a backdrop (§6 観察 1, C-1665).

Giant is made by *not* showing all of it: legs and tail crossing the
frame, and the full body saved for a moment. The kaiju is built that way -
thirty frames of the awakening, then never again until it is down, and the
page says so in a comment.

The contract only ever checked that the wide shot happens. Drawing it on
every frame left 231 kaiju/awakening/boss tests green, so the way this
template makes its size could be deleted without reddening a number. That
is the fourth one-directional contract this session (C-1637's hold,
C-1652's ladder, C-1662's latch): each checked that a thing appears and
never that it stops.

Counted off the canvas, not the source: the wide shot is a body 60 wide,
shoulders 88 wide and a head of radius 26, together in one frame.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import wide_probe


@pytest.fixture(scope="module")
def watched() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=wide_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_whole_creature_stands_up_in_the_awakening(watched) -> None:
    assert watched["wake"] > 0, watched


def test_it_is_a_moment_inside_the_awakening_not_the_whole_of_it(watched) -> None:
    """The first version of this only refused *literally every* frame, and
    an awakening filled end to end - 88 of 89 - walked through it by one
    frame. "要所に 1 回だけ" is a claim about brevity, so the bound has to
    be one."""

    assert watched["wake"] * 2 < watched["wakeFrames"], watched


def test_it_is_not_on_screen_during_the_fight(watched) -> None:
    assert watched["fight"] == 0, watched


def test_the_fight_was_watched_long_enough_to_mean_something(watched) -> None:
    """Shooting ends the round in about twenty frames, and "it never
    appeared" across twenty frames is evidence of nothing. The probe
    stands off and watches instead, so the absence is measured over a
    real stretch."""

    assert watched["fightFrames"] >= 120, watched


def test_a_reset_never_gets_counted_as_the_fight(watched) -> None:
    """A dead cannon resets the page, and the fresh awakening draws the
    wide shot again - which would look exactly like the fault this test
    exists to find. The probe keeps the cannon alive; if the round ever
    ended back at the opening mid-count this would be the tell."""

    assert watched["fightFrames"] > 0
    assert not watched["shown"], watched
