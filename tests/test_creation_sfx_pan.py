"""The sound comes from where it happened (§2 増築, C-1394).

All twelve voices played dead centre while the screen always had a left
and a right. Now a caller that knows a screen position hands sfx a
normalised x, and one StereoPannerNode places the sound - clamped to
±0.8, graceful where the node is missing, and positionless sounds keep
the old centre path with no panner built at all.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.catchgame import pan_probe as catch_pan
from sidra_ai.creation.fishing import pan_probe as fishing_pan
from sidra_ai.creation.kaiju import pan_probe as kaiju_pan
from sidra_ai.creation.shooter import pan_probe as shooter_pan

_PROBES = {"shooter": shooter_pan, "kaiju": kaiju_pan,
           "fishing": fishing_pan, "catch": catch_pan}
_REQUESTS = {"shooter": "ゲームを作って", "kaiju": "巨大怪獣と戦うゲームを作って",
             "fishing": "魚釣りゲームを作って", "catch": "フルーツキャッチを作って"}


def _drive(template: str) -> dict:
    kwargs = {"template": template} if template in ("shooter", "kaiju") else {}
    html = generate_game(_REQUESTS[template], **kwargs).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=_PROBES[template](script),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", ["shooter", "kaiju", "fishing", "catch"])
def test_positionless_sounds_build_no_panner(template: str) -> None:
    got = _drive(template)
    assert got["before"] == 0, "a positionless sound built a panner"


def test_shooter_kills_pan_left_and_right_to_the_digit() -> None:
    got = _drive("shooter")
    assert got["kills"] == 2, "the engineered kills never landed"
    assert len(got["pans"]) == 2
    for pan, want in zip(got["pans"], got["expected"]):
        assert abs(pan - want) < 1e-9, "the ear points wrong"
    assert got["pans"][0] > 0 > got["pans"][1], "left and right do not separate"


def test_kaiju_leg_hit_pans_to_the_leg() -> None:
    got = _drive("kaiju")
    assert got["state"] == "fight"
    assert len(got["pans"]) == 1, "the leg hit never panned"
    assert abs(got["pans"][0] - got["expected"]) < 1e-9, "the ear points wrong"
    assert got["pans"][0] > 0, "the monster stands right of centre"


@pytest.mark.parametrize("template", ["fishing", "catch"])
def test_the_horizontal_games_pan_to_their_own_x(template: str) -> None:
    """C-1396: the sweep marker and the falling fruit carry the position."""

    got = _drive(template)
    exp = got["expected"]
    assert len(got["pans"]) == len(exp), "a placed event never panned"
    for pan, want in zip(got["pans"], exp):
        assert abs(pan - want) < 1e-9, "the ear points wrong"
