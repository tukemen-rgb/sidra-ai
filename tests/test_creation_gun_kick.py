"""The gun kicks back (§1×§23 事実 3, C-1380).

Nijman's technique table counts firing recoil ("Gun delay & kickback")
apart from being hit (knockback): the duel's release has had its snap
since C-1358, while the shooter's shoot() and the kaiju's fire() pushed
shots out of a perfectly rigid body. Now one real shot kicks the hull
back three pixels, or sinks the walker to 0.94 through the same squash
channel the stomp crush uses - and under reduced motion the same shot
fires with the body perfectly still.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.kaiju import kick_probe as kaiju_kick
from sidra_ai.creation.shooter import kick_probe as shooter_kick

_PROBES = {"shooter": shooter_kick, "kaiju": kaiju_kick}
_REST = {"shooter": 0.0, "kaiju": 1.0}


def _drive(template: str, *, reduced: bool) -> dict:
    html = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"],
        input=_PROBES[template](script, reduced=reduced),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_one_shot_kicks_and_settles(template: str) -> None:
    got = _drive(template, reduced=False)
    assert got["shots"] == 1, "the trigger did not fire exactly one shot"
    assert got["onFire"] != got["idle"], "the shot moves nothing"
    assert got["trace"][-1] == _REST[template], "the recoil never settles"


@pytest.mark.parametrize("template", ["shooter", "kaiju"])
def test_reduced_motion_fires_with_a_still_body(template: str) -> None:
    got = _drive(template, reduced=True)
    assert got["shots"] == 1, "reduced motion must not cost the shot itself"
    assert got["onFire"] == got["idle"], "reduced motion still kicks"
