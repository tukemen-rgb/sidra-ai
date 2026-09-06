"""The hit throws the body, not just the camera (§1, C-1361).

The technique list pairs hitstop with knockback, and only the adventure's
hero had both. The kaiju soldier and the shooter ship now take an impulse
away from the impact, decaying by quarters inside half a second, clamped
by the same bounds steering respects.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import kb_probe as kaiju_probe
from sidra_ai.creation.shooter import kb_probe as shooter_probe

_CASES = {
    "kaiju": ("巨大怪獣と戦うゲームを作って", kaiju_probe, 30.0),
    "shooter": ("シューティングゲームを作って", shooter_probe, 22.0),
}


@pytest.fixture(scope="module")
def thrown() -> dict[str, dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    out: dict[str, dict] = {}
    for key, (request, probe, _bound) in _CASES.items():
        page = generate_game(request).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        assert script is not None, key
        run = subprocess.run(
            ["node", "-"],
            input=probe(script.group(1)),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert run.returncode == 0, f"{key}: {run.stderr[:400]}"
        out[key] = json.loads(run.stdout.strip().splitlines()[-1])
    return out


@pytest.mark.parametrize("key", sorted(_CASES))
def test_the_hit_throws_the_body_away(thrown: dict, key: str) -> None:
    seen = thrown[key]
    assert seen["hpBefore"] - seen["hpAfter"] == 1, "one hit, one heart"
    assert seen["onHit"]["kvx"] < 0, "the impulse points away from the impact"
    assert seen["moved"] >= 12, f"the throw is a twitch ({seen['moved']:.1f}px)"


@pytest.mark.parametrize("key", sorted(_CASES))
def test_the_body_settles_and_the_wall_holds(thrown: dict, key: str) -> None:
    seen = thrown[key]
    assert seen["settledKvx"] == 0, "control never fights a phantom drift"
    bound = _CASES[key][2]
    assert seen["minX"] >= bound, "the bound holds against the throw"
