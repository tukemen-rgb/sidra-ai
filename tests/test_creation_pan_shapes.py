"""Agreement has more than one shape (§28, C-1658).

C-1650 and C-1653 asked one question - does the light land where the pan
says - and it fits six of the nine panned sites. Asking it of the other
three would fail two pages that are right:

* the puzzle rings at the CENTRE of the group it cleared and lights every
  tile in it, which is C-1418's rule that a big clear's number appears
  where the big clear was. The honest question is containment.
* the marble pans by LANE and draws at the PROJECTED x, because at gate
  range the projection magnifies so far that screen x would saturate the
  panner - its own comment says so. Their numbers are not comparable; the
  direction they step in is.

This is the fourth time the same judgement has come up (C-1645's "exactly
[0,1,2]" against a boss that cycles, C-1652's same-frame company, C-1653's
coordinate spaces): a contract has to be able to pass a correct
implementation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import beats_probe
from sidra_ai.creation.marble import ladder_probe as marble_ladder
from sidra_ai.creation.puzzle import slope_probe as puzzle_slope


def _driven(request: str, builder) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=builder(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_the_monster_rings_and_lights_at_one_point() -> None:
    pair = _driven("巨大怪獣と戦うゲームを作って", beats_probe)["pair"]

    assert pair is not None and not pair["litNothing"]
    assert pair["sameSide"], pair
    assert pair["apartPx"] <= 8, pair


def test_the_puzzle_rings_inside_what_it_lit() -> None:
    """Not on one tile - between them, because that is where the clear was."""

    span = _driven("パズルゲームを作って", puzzle_slope)["heavy"]["span"]

    assert span is not None and not span["litNothing"]
    assert span["lit"] >= 2, span
    assert span["inside"], span


def test_the_puzzles_span_is_really_a_span() -> None:
    """If the span collapsed to a point this would silently become the
    coincidence test, and the containment it is meant to check would go
    unexercised."""

    span = _driven("パズルゲームを作って", puzzle_slope)["heavy"]["span"]

    assert span["hi"] > span["lo"], span


def test_the_marble_steps_both_channels_the_same_way() -> None:
    together = _driven("玉転がしゲームを作って", marble_ladder)["together"]

    assert together is not None, "two gates could not be rolled"
    assert together["moved"], together
    assert together["sameWay"], together


def test_the_marble_is_not_judged_on_position() -> None:
    """Its two channels are in different spaces; a position comparison
    would fail a page whose comment explains why it is right."""

    import pathlib

    import scripts.product_metrics as _pm  # noqa: F401

    text = pathlib.Path(_pm.__file__).read_text(encoding="utf-8")
    block = text[text.index("marble/ゲート") :][:600]

    assert "sameWay" in block
    assert "apartPx" not in block
