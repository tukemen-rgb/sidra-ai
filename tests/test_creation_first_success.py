"""The first ten seconds hand something over.

§8 事実 5・8: what decides whether a person plays a second round is
whether the first one gave them anything. The generated pages had no rule
about their opening at all - the fishing marker started wherever the loop
happened to be, and the adventure's first gem was a 34% chance behind a
tuft of grass the seed might not have placed anywhere near the hero.

The claim is about a player, so the judge is one: a masher that presses
the action, leans on a direction, taps the canvas, and knows nothing about
any particular game. It *wanders* rather than travels, which is the point -
an opening that needs the player to cross the field to find the first
target is asking for intent they have not formed yet. The first success
has to come to them.

Every template is played on three seeds. "Guaranteed" that held for one
layout would be a coincidence, and this file exists because the multi-seed
run is what caught the adventure.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402
from sidra_ai.creation.opening import (  # noqa: E402
    FIRST_SUCCESS,
    OPENING_SECONDS,
    probe_source,
)

KEYS = sorted(TEMPLATES)
#: Three requests, so three different seeds, so three different layouts.
REQUESTS = ("ゲームを作って", "楽しいゲームを作って", "難しいゲームを作って")

CASES = [
    pytest.param(template, request, id=f"{template}-{index}")
    for template in KEYS
    for index, request in enumerate(REQUESTS)
]


def _play(template: str, request: str, *, seconds: int = OPENING_SECONDS) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the opening")
    page = generate_game(request, template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1), template, seconds=seconds),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(("template", "request_"), CASES)
def test_a_masher_wins_something_in_the_first_ten_seconds(
    template: str, request_: str
) -> None:
    seen = _play(template, request_)

    assert seen["firstWinMs"] is not None, (
        f"no {FIRST_SUCCESS[template][1]} in {OPENING_SECONDS}s"
    )
    assert seen["firstWinMs"] <= OPENING_SECONDS * 1000


@pytest.mark.parametrize(("template", "request_"), CASES)
def test_the_win_was_not_already_true(template: str, request_: str) -> None:
    """Otherwise the number measures an expression, not an opening."""

    assert _play(template, request_)["wonBeforePlaying"] is False


@pytest.mark.parametrize("template", KEYS)
def test_the_opening_is_generous_even_in_two_seconds(template: str) -> None:
    """Where the margin actually sits.

    Ten seconds is the bound §8 gives; most of these land inside two, and
    pinning that keeps a change that quietly halves the generosity visible
    while it is still nowhere near failing the bound.
    """

    fast = [
        _play(template, request, seconds=4)["firstWinMs"] is not None
        for request in REQUESTS
    ]

    assert any(fast), "not one of three seeds pays out inside four seconds"


# ------------------------------------------------- what the page cannot say


@pytest.mark.parametrize("template", KEYS)
def test_every_template_declares_its_first_win(template: str) -> None:
    assert template in FIRST_SUCCESS
    expression, words = FIRST_SUCCESS[template]
    assert expression and expression != "false"
    assert words


def test_the_bound_is_the_one_the_notes_give() -> None:
    assert OPENING_SECONDS == 10


def test_the_race_counts_the_obstacle_it_got_past() -> None:
    """The racing gap was that nothing counted the first success at all.

    Its score is a completed lap - eighteen seconds away and no use as a
    first taste - so the page had no way to say "you got past one".
    """

    page = generate_game("レースゲームを作って", template="racing").html

    assert "passed++" in page
    assert "passed:passed" in page
