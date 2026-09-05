"""The body of the jump (§1, C-1332).

Squash & stretch - the first principle of animation, and the one item on
§1's technique list that existed nowhere - lands on the template whose
whole craft is the jump. One real jump, watched frame by frame: stretch
on the way up, squash on the exact landing frame, settled half a second
later, and dead still while standing. Under reduced motion the silhouette
never changes at all.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.platformer import squash_probe


def _jumped(request: str = "ジャンプアクションを作って", *, reduced: bool = False) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=squash_probe(script.group(1), reduced=reduced),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "request_", ["ジャンプアクションを作って", "難しいジャンプアクションを作って"]
)
def test_the_jump_stretches_and_the_landing_squashes(request_: str) -> None:
    jumped = _jumped(request_)

    assert jumped["restSq"] == 1
    assert jumped["riseMax"] > 1.1, "the take-off never stretched"
    assert jumped["landSq"] is not None and jumped["landSq"] < 0.9, (
        "the landing never squashed"
    )


def test_the_bounce_settles_and_the_idle_is_still() -> None:
    jumped = _jumped()

    assert jumped["settled"] == pytest.approx(1, abs=0.02)
    assert jumped["idleMax"] == 0, "the body breathes while standing still"


def test_reduced_motion_keeps_the_silhouette() -> None:
    jumped = _jumped(reduced=True)

    assert jumped["restSq"] == 1
    assert jumped["riseMax"] in (0, 1)
    assert (jumped["landSq"] or 1) == 1
    assert jumped["idleMax"] == 0
