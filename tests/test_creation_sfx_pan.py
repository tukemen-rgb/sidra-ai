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
from sidra_ai.creation.adventure import pan_probe as adventure_pan
from sidra_ai.creation.duel import pan_probe as duel_pan
from sidra_ai.creation.fishing import pan_probe as fishing_pan
from sidra_ai.creation.kaiju import pan_probe as kaiju_pan
from sidra_ai.creation.marble import pan_probe as marble_pan
from sidra_ai.creation.racing import pan_probe as racing_pan
from sidra_ai.creation.shooter import pan_probe as shooter_pan

_PROBES = {"shooter": shooter_pan, "kaiju": kaiju_pan,
           "fishing": fishing_pan, "catch": catch_pan, "duel": duel_pan,
           "marble": marble_pan, "racing": racing_pan,
           "adventure": adventure_pan}
_REQUESTS = {"shooter": "ゲームを作って", "kaiju": "巨大怪獣と戦うゲームを作って",
             "fishing": "魚釣りゲームを作って", "catch": "フルーツキャッチを作って",
             "duel": "光線で撃ち合う対戦ゲームを作って",
             "marble": "玉転がしゲームを作って",
             "racing": "レースゲームを作って",
             "adventure": "迷宮を冒険するゲームを作って"}


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


@pytest.mark.parametrize(
    "template",
    ["shooter", "kaiju", "fishing", "catch", "duel", "marble", "racing",
     "adventure"],
)
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


def test_duel_hits_tell_left_from_right() -> None:
    """C-1398: the one template whose subject IS left versus right."""

    got = _drive("duel")
    assert got["eHp"] == 2 and got["pHp"] == 2, "a volley never landed"
    assert len(got["pans"]) == 2
    for pan, want in zip(got["pans"], got["expected"]):
        assert abs(pan - want) < 1e-9, "the ear points wrong"
    assert got["pans"][0] > 0 > got["pans"][1], "the sides do not separate"


def test_marble_gates_tell_left_from_right() -> None:
    """C-1616: the pan is the LANE position, not the screen x.

    A gate scores almost level with the ball, and the projection at that
    range magnifies a wide gate to -540 on a 720 canvas - screen x would
    saturate the panner at every gate that is not dead ahead.
    """

    got = _drive("marble")
    assert got["gates"] == 2, "the engineered gates never scored"
    assert len(got["pans"]) == 2
    for pan, want in zip(got["pans"], got["expected"]):
        assert abs(pan - want) < 1e-9, "the ear points wrong"
    assert got["pans"][0] < 0 < got["pans"][1], "the lane does not separate"


def test_racing_places_the_crash_and_the_slipstream() -> None:
    """C-1616: which side you clipped, and which side you shaved past."""

    got = _drive("racing")
    assert got["crashes"] == 2, "the engineered crashes never landed"
    assert got["slips"] == 1, "the engineered slipstream never paid"
    assert len(got["pans"]) == 3
    for pan, want in zip(got["pans"], got["expected"]):
        assert abs(pan - want) < 1e-9, "the ear points wrong"
    assert got["pans"][0] != got["pans"][1], "both crashes sound identical"


def test_the_maze_tells_which_side_the_blow_landed() -> None:
    """The eighth body (§2 増築, C-1630), and the third time the shape has
    repeated: the roamer's x was already going to ``burst`` on the line
    that killed it, and the ear got nothing."""

    got = _drive("adventure")

    assert [c["name"] for c in got["left"]] == ["sword", "hurt"]
    assert [c["name"] for c in got["right"]] == ["sword", "hurt"]
    assert got["left"][1]["pan"] < 0 < got["right"][1]["pan"]
    assert got["pans"] == pytest.approx(got["expected"], abs=1e-9)


def test_the_sword_is_heard_where_the_blade_lands() -> None:
    """Not where the hero stands. The probe puts the hero 20px short of the
    target, so the two coordinates give different numbers and only one of
    them is right."""

    got = _drive("adventure")
    blade = got["left"][0]["pan"]
    hero_would_be = ((104 - 20) / 720 * 2 - 1) * 0.8

    assert blade == pytest.approx(got["expected"][0], abs=1e-9)
    assert blade != pytest.approx(hero_would_be, abs=1e-6)


def test_the_maze_keeps_its_words_in_the_middle() -> None:
    """Read out by the page's own line - swinging at a tablet - because a
    probe that calls ``sfx('step')`` itself only proves the probe can."""

    got = _drive("adventure")

    assert [c["name"] for c in got["quiet"]] == ["step"]
    assert [c["pan"] for c in got["quiet"]] == [None]
