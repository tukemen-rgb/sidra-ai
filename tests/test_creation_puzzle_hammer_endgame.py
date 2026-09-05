"""C-1428: the comeback tool is a move, so the go waits for it.

Found by measuring C-1427 rather than by reading: a greedy round stranded
17 tiles while still holding 3 hammers. ``movesLeft()`` looked only for a
group of two, but a hammer breaks a lone tile and the collapse that follows
can put two of a colour beside each other again - so the go was ending
while the tool the code itself calls "the classic comeback tool" sat
unspent in the purse.

Measured both ways on the same page, because "it no longer ends" is only a
result if the other drive does end: the hoarder clears groups and never
touches a lone tile, and the spender does the same and then spends.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.puzzle import recap_probe_source

ASK = "パズルゲームを作って"


def _drive(spend: bool):
    found = re.search(r"<script>(.*?)</script>", generate_game(ASK).html, re.S)
    assert found is not None
    run = subprocess.run(
        ["node", "-"],
        input=recap_probe_source(found.group(1), spend=spend),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert run.returncode == 0, run.stderr[:400]
    out = run.stdout.strip().splitlines()
    return json.loads(out[-2]), json.loads(out[-1])


@pytest.fixture(scope="module")
def drives():
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    return {"hoard": _drive(False), "spend": _drive(True)}


def test_the_hoarder_reaches_the_old_deadlock(drives) -> None:
    """Without this, "still playing" would say nothing about the rule."""

    _, tail = drives["hoard"]
    assert tail["bestN"] < 2, "there was still a group to clear"
    assert tail["livePurse"] > 0, "nothing was banked, so nothing was held"


def test_holding_a_hammer_is_not_a_jam(drives) -> None:
    end, tail = drives["hoard"]
    assert not end["lost"], f"jammed while holding {tail['livePurse']} hammers"


def test_spending_the_purse_still_ends_the_go(drives) -> None:
    """The other direction: the round is finishable, so "not over" above is
    the purse rather than a loop that never ends."""

    end, tail = drives["spend"]
    assert end["lost"]
    assert tail["livePurse"] == 0, "the jam still held a hammer"


def test_the_extra_moves_open_real_tiles(drives) -> None:
    _, hoard = drives["hoard"]
    _, spend = drives["spend"]
    assert spend["broken"] > 0, "no tile was opened with a hammer"
    assert spend["recount"] < hoard["recount"], (
        f"spending opened nothing: {spend['recount']} left "
        f"against the hoarder's {hoard['recount']}"
    )
