"""The act raises the band too (§6 観察 3, C-1383).

The fall, the roll, the sky's brightness and even the engine's pitch all
step by thirds, while the four bars walked the whole round at one pace.
Now the scheduler's stride divides by [1, 1.08, 1.15] per act - with act
0 exactly the old pace, so every deterministic probe window is
bit-identical - and multiplies with the combat double, so a final-act
fight is the fastest music of the run.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.music import tempo_probe


@pytest.fixture(scope="module")
def trodden() -> dict:
    html = generate_game("釣りゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=tempo_probe(script),
        capture_output=True, text=True, timeout=300,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_act_zero_is_exactly_the_old_pace(trodden: dict) -> None:
    assert trodden["t0"] == 1
    assert trodden["step"] == 0.27, "the base stride itself drifted"


def test_the_final_act_treads_faster(trodden: dict) -> None:
    assert trodden["t2"] == 1.15, "act 2 never reaches its tempo"
    assert trodden["walked2"] > trodden["walked0"]
    assert 1.10 <= trodden["ratio"] <= 1.22, (
        f"the tread ratio is off the table ({trodden['ratio']:.2f})"
    )
