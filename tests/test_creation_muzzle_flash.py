"""The muzzle lights up (§1×§23 事実 4, C-1391).

The talk's bullet trio - bigger bullets, muzzle flash, faster bullets -
had its middle member nowhere: shots, recoil (C-1380) and trails (C-1389)
all landed while the muzzle stayed dark. Now one real shot lights the
nose/cannon for exactly two frames at 0.85 alpha and goes dark again, the
idle gun never lights, and reduced motion fires the same shot dark.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.kaiju import muzzle_probe as kaiju_muzzle
from sidra_ai.creation.shooter import muzzle_probe as shooter_muzzle

_PROBES = {"shooter": shooter_muzzle, "kaiju": kaiju_muzzle}
_REQUESTS = {"shooter": "ゲームを作って", "kaiju": "巨大怪獣と戦うゲームを作って"}


def _drive(template: str, *, reduced: bool) -> dict:
    html = generate_game(_REQUESTS[template], template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=_PROBES[template](script, reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_one_shot_lights_two_frames_then_goes_dark(template: str) -> None:
    got = _drive(template, reduced=False)
    assert got["shots"] == 1, "the trigger did not fire exactly one shot"
    assert not got["idleFlash"], "the idle muzzle glows"
    assert got["lit"] == [True, True, False, False], "the flash misfires"


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_reduced_motion_fires_with_a_dark_muzzle(template: str) -> None:
    got = _drive(template, reduced=True)
    assert got["shots"] == 1, "reduced motion must not cost the shot itself"
    assert not got["idleFlash"] and not any(got["lit"]), (
        "reduced motion still flashes"
    )
