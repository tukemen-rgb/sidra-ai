"""The sinks stay affordable in the worst case (§5, C-1376).

§5's source makes tap/sink balance the rule, and balance has a worst
case: the adventure's only tap is a handful of tufts that never regrow,
so before the pity floor about one run in twenty-nine ended below the
shrine's 3 gems - the sink C-1021 built turned into a signboard for
that run, and the player could not know why.

Driven with loaded dice: rand is forced after the world is built, so
the same blade cuts the same tufts and only the drop rolls change.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.adventure import econ_probe as adv_econ
from sidra_ai.creation.platformer import econ_probe as plat_econ


def _script(request: str, template: str) -> str:
    html = generate_game(request, template=template).html
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


def _run(source: str) -> dict:
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=180
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_dry_run_still_buys_the_shrine_and_the_door() -> None:
    got = _run(adv_econ(_script("ゲームを作って", "adventure"), dice=0.99))
    assert got["cuts"] == got["grass"], "the blade missed tufts"
    assert got["gems"] >= 5, (
        f"the unluckiest run banks {got['gems']} gems - "
        "below the shrine's 3 plus the door's 2"
    )
    assert got["shrine"]["maxhpAfter"] == got["shrine"]["maxhpBefore"] + 1
    assert got["shrine"]["gemsAfter"] == got["shrine"]["gemsBefore"] - 3


def test_the_floor_does_not_leak_into_lucky_runs() -> None:
    got = _run(adv_econ(_script("ゲームを作って", "adventure"), dice=0.0))
    assert got["gems"] == got["grass"] + 1, (
        "an always-hit run should bank exactly one gem per tuft "
        "(plus the opening cut) - pity must never double-pay"
    )


@pytest.mark.parametrize(
    "request_text",
    ["ゲームを作って", "難しいゲームを作って", "やさしいゲームを作って"],
)
def test_the_low_road_affords_the_lamp(request_text: str) -> None:
    got = _run(plat_econ(_script(request_text, "platformer")))
    assert got["low"] >= got["cost"], (
        f"the low road holds {got['low']} gems against a "
        f"{got['cost']}-gem lamp - the shelf's {got['shelf']} must not be needed"
    )
