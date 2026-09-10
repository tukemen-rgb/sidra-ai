"""Heavier events kick the camera harder (§1, C-1648).

§1 quotes Vlambeer's rule directly: kick the camera a few pixels on an
explosion or a heavy hit, decay it fast, and make the shake *proportional
to the weight of the event*. The decay half was wired from the start. The
proportion half was never asked for - the only place a shake reached a
contract was the fail beat having to clear ``max(every shake literal in
every template)``, which draws one ceiling and says nothing about the
order underneath it. Flattening the kaiju's five weights (3/5/6/7/9) to a
single 9 left 292 tests green.

Read the way C-1640 taught: not the literals in the source, which are the
ledger, but what the page's own ``shakeAmount()`` returned when the event
was actually driven.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.adventure import knock_probe
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import beats_probe


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


@pytest.fixture(scope="module")
def dungeon() -> dict:
    return _driven("冒険ゲームを作って", knock_probe)


@pytest.fixture(scope="module")
def monster() -> dict:
    return _driven("巨大怪獣と戦うゲームを作って", beats_probe)


def test_the_guardian_kicks_the_camera_harder_than_a_roamer(dungeon) -> None:
    light = dungeon["roamOpen"]["shake"]
    heavy = dungeon["guardOpen"]["shake"]

    assert heavy > light, (heavy, light)


def test_the_head_kicks_the_camera_harder_than_the_leg(monster) -> None:
    light = monster["leg"]["kick"]
    heavy = monster["head"]["kick"]

    assert heavy > light, (heavy, light)


@pytest.mark.parametrize("which", ["roamOpen", "guardOpen"])
def test_both_of_the_dungeons_blows_actually_kick(dungeon, which) -> None:
    """A pair that never fired is not a pass, it is a pair that was never
    measured (C-1637), and it would let "no shake at all" through."""

    assert dungeon[which]["hit"], which
    assert dungeon[which]["shake"] > 0, which


@pytest.mark.parametrize("which", ["leg", "head"])
def test_both_of_the_monsters_blows_actually_kick(monster, which) -> None:
    assert monster[which]["landed"], which
    assert monster[which]["kick"] > 0, which


def test_the_contract_reads_the_page_not_the_source() -> None:
    """The ladder must come from shakeAmount(), not from a regex over the
    template source - that is the ledger C-1640 stopped trusting."""

    import pathlib

    import scripts.product_metrics as _pm  # noqa: F401

    text = pathlib.Path(_pm.__file__).read_text(encoding="utf-8")
    block = text[text.index("ladder_gaps: list[str] = []") :]
    block = block[: block.index('"creation_shake_ladder"')]

    assert "shake" in block
    assert "findall" not in block, "the ladder must not be read off the source"
