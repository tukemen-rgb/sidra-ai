"""The other two juice channels are weighed too (§1, C-1660).

§1 lists the kit as siblings - shake, particles, hitstop.
``creation_shake_scales_with_input`` (C-1657) weighs the first. The pages
weigh the other two as well: the platformer's landing dust is
``min(12, 2+round(vBefore))`` so a hop puffs and a drop throws up a cloud,
and the puzzle's freeze steps at ``cells.length > 4``. Neither was asked
for - flattening both to constants left 204 tests green.

Everything here is read off the page's own state: juice's ``PARTS`` list
and its ``HITSTOP`` counter. The number handed to ``burst()`` is the
ledger, and this is the third cycle in a row where reading the ledger
would have proved nothing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import ladder_probe as plat_ladder
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


def test_a_heavier_landing_throws_up_more_dust() -> None:
    seen = _driven("ジャンプで進むゲームを作って", plat_ladder)
    soft, hard = seen["softDust"], seen["hardDust"]

    assert soft and hard, "the two landings were not driven"
    assert hard["vy"] > soft["vy"], (soft, hard)
    assert hard["parts"] > soft["parts"], (soft, hard)


def test_each_landing_is_read_on_its_own_frame() -> None:
    """A combo step-up adds twelve particles of its own, so a reading taken
    while one was in the air is not this landing's dust."""

    seen = _driven("ジャンプで進むゲームを作って", plat_ladder)

    for half in ("softDust", "hardDust"):
        assert seen[half]["rang"] == ["step"], (half, seen[half]["rang"])


def test_a_bigger_clear_throws_up_more_dust() -> None:
    seen = _driven("パズルゲームを作って", puzzle_slope)
    light, heavy = seen["light"], seen["heavy"]

    assert heavy["size"] > light["size"]
    assert heavy["parts"] > light["parts"], (light, heavy)
    for half in (light, heavy):
        assert half["rang"] == ["gem"], half["rang"]


def test_a_clear_over_the_step_freezes_longer() -> None:
    """The step is `cells.length > 4`, so the pair used above sits on one
    side of it. This is the reading that crosses."""

    seen = _driven("パズルゲームを作って", puzzle_slope)
    light, crossed = seen["light"], seen["crossed"]

    assert light["size"] <= 4 < crossed["size"], (light, crossed)
    assert crossed["held"] > light["held"], (light, crossed)


def test_the_dust_is_not_read_from_the_crossing_clear() -> None:
    """That clear rings a combo step-up, which adds twelve particles but
    touches HITSTOP not at all - so the freeze may be read there and the
    dust may not. If this ever stops being true the contract has to move."""

    seen = _driven("パズルゲームを作って", puzzle_slope)
    crossed = seen["crossed"]

    assert len(crossed["rang"]) > 1, "expected company on the crossing frame"
    assert crossed["parts"] > seen["heavy"]["parts"], crossed
