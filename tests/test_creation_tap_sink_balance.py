"""The tap and the sink have to balance (§5, C-1696).

§5's fact is an economy one and its word is 釣り合い: taps (where the
resource comes in) and sinks (where it goes out) in balance. Its learning
is what happens when they are not - 「収集物に意味のあるゲーム内目的が
無ければ、プレイヤーは収集物どころかゲーム自体への興味を失う」.

Three judges cover the outlet: it exists (C-1021), a player can always
afford it (C-1376), and it returns value (C-1674). All three, plus the
affordability floor, look at one side. Make a tuft drop ten gems and the
board stays green while the shrine and the door stop being choices.

Both sides are read by playing: the village cut bare for the inlet, and
each outlet priced by actually paying it. Neither number comes from a
constant - a price nobody pays is a ledger entry.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import sink_probe
from sidra_ai.creation.games import generate_game

CEILING = 3.0


@pytest.fixture(scope="module")
def economy() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to cut the village")
    html = generate_game("迷宮を冒険するゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=sink_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert got.returncode == 0, got.stderr[:400]
    seen = json.loads(got.stdout.strip().splitlines()[-1])
    seen["sinks"] = seen["heartPrice"] * seen["heartsForSale"] + seen["doorCost"]
    return seen


def test_both_sides_were_read_by_playing(economy: dict) -> None:
    assert economy["purse"] > 0, "the village paid nothing"
    assert economy["heartPrice"] > 0 and economy["heartsForSale"] > 0
    assert economy["doorCost"] > 0, "the door is not an outlet"


def test_the_outlets_can_be_paid(economy: dict) -> None:
    """The floor. Below it the outlets are decoration."""

    assert economy["purse"] >= economy["sinks"], (
        economy["purse"],
        economy["sinks"],
    )


def test_the_gems_do_not_outrun_the_outlets(economy: dict) -> None:
    """The ceiling, which nothing measured. Above it the shrine and the
    door stop being choices and the gems go back to being a number."""

    ratio = economy["purse"] / economy["sinks"]
    assert ratio <= CEILING, (economy["purse"], economy["sinks"], ratio)


def test_the_shrine_stops_selling_at_the_ceiling(economy: dict) -> None:
    """Why the outlet total is finite at all (C-1674): the shrine refuses
    once the hearts are full, so the inlet cannot be balanced by simply
    letting a player buy forever."""

    refused = [b for b in economy["buys"] if b["gemsAfter"] == b["gemsBefore"]]
    assert refused, "the shrine never refused, so the outlet has no total"
    assert economy["heartsForSale"] == 2, economy["heartsForSale"]
