"""C-1427: the puzzle says why the board jammed.

``LOSS_UNWIRED`` had this template down as "'over' means the board jammed,
but nothing counts *why* it jammed yet". The axis was **measured before it
was chosen**: at the jam every tile still standing is a group of one. That
is what "no moves" means in a game where nothing spawns and nothing falls
in from above - the board only empties, so nothing fills up and there is no
column to blame.

The two causes are deliberately commensurable: both count tiles, and
together they are the whole stranded board, so "the largest cause" is a
real comparison rather than two different units being ranked against each
other. Which one wins says something different - a purse of unspent
hammers is a tool that went unused; a remainder past it is a board that
nothing on hand could have opened.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.puzzle import recap_probe_source
from sidra_ai.creation.recap import LOSS_UNWIRED, LOSS_WIRED, WIN_EXTRA, probe_source

ASK = "パズルゲームを作って"


def test_the_template_is_wired_rather_than_excused() -> None:
    assert "puzzle" in LOSS_WIRED
    assert "puzzle" not in LOSS_UNWIRED
    assert len(LOSS_WIRED["puzzle"]["causes"]) == 2
    # Clearing the board ends in the same state a jam does, so the flag is
    # the whole difference between the win and the loss.
    assert "cleared" in LOSS_WIRED["puzzle"]["lost"]
    assert WIN_EXTRA["puzzle"] == "cleared = true"


def test_a_probe_without_a_route_is_unchanged() -> None:
    plain = probe_source("/* page */", template="shooter")
    assert "WIN_EXTRA_TOKEN" not in plain
    assert "pzStep" not in plain


@pytest.fixture(scope="module")
def jammed():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    found = re.search(r"<script>(.*?)</script>", generate_game(ASK).html, re.S)
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=recap_probe_source(found.group(1)),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert run.returncode == 0, run.stderr[:400]
    out = run.stdout.strip().splitlines()
    return json.loads(out[-2]), json.loads(out[-1])


def test_the_driven_board_jams_with_a_reason(jammed) -> None:
    main, _ = jammed
    assert main["atEnd"]["lost"]
    assert main["atEnd"]["line"]
    assert not main["verdictWhileLive"]


def test_every_stranded_tile_is_alone(jammed) -> None:
    """The definition of the jam, checked rather than assumed."""

    _, tail = jammed
    assert tail["recount"] > 0, "an empty board is a clear, not a jam"
    assert tail["singles"] == tail["recount"]


def test_the_snapshot_matches_the_board_it_summarises(jammed) -> None:
    _, tail = jammed
    assert tail["tiles"] == tail["recount"]
    assert tail["jamColours"] == tail["colours"]
    # The purse against the one the game still holds - nothing can spend a
    # hammer after the board is over. Since C-1428 both are zero at a jam,
    # because holding one means the go is not over; the equality is still
    # what stops a snapshot that never records the purse from agreeing with
    # a line derived from it.
    assert tail["hammers"] == tail["livePurse"]


def test_the_line_reports_the_larger_half_and_reaches_the_strip(jammed) -> None:
    main, tail = jammed
    want = max(tail["broken"], tail["tiles"])
    assert str(want) in main["atEnd"]["line"]
    assert main["atEnd"]["line"] in main["strip"]


def test_the_largest_cause_is_a_comparison(jammed) -> None:
    """A go that opened more tiles than it stranded is not something a drive
    reaches, so the honest way to ask is to move the counter and read the
    same page again - and the count printed has to follow it."""

    _, tail = jammed
    assert "ハンマー" in tail["saidPurse"]
    assert str(tail["tiles"] + 5) in tail["saidPurse"]


def test_both_causes_at_zero_says_nothing(jammed) -> None:
    _, tail = jammed
    assert tail["saidNothing"] == ""


def test_a_cleared_board_is_not_explained(jammed) -> None:
    main, _ = jammed
    assert main["afterWin"]["lost"] is False
    assert main["afterWin"]["line"] == ""
