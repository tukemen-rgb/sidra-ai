"""A held key keeps the basket moving (§12 事実 3, C-1328).

The on-screen pad synthesises no key repeat - one press is exactly one
keydown - so the catch template, the only one of the ten that moved its
player inside the keydown event, stood still under a held ◀ on the pad's
own audience. These tests press the way the pad presses and read the
basket off the running page: the tap nudge survives, an OS auto-repeat is
not a second nudge, the drift continues every frame while held, stops on
release, and the field edge holds.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.catchgame import hold_probe
from sidra_ai.creation.games import generate_game


def _held(request: str = "キャッチゲームを作って") -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=hold_probe(script.group(1)),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def test_a_single_keydown_keeps_the_basket_moving():
    """One press with no repeats - the pad's press - must keep moving."""

    held = _held()

    assert held["px0"] - held["pxNudge"] == pytest.approx(0.06, abs=0.001)
    assert held["pxNudge"] - held["pxHeld"] >= 0.3, "the hold went nowhere"


def test_an_os_auto_repeat_is_not_a_second_step():
    """Desktop repeats arrive as extra keydowns; the flag swallows them."""

    held = _held()

    assert held["pxNudge"] - held["pxRepeat"] <= 0.001


def test_release_stops_the_basket_and_the_edge_holds():
    held = _held("難しいキャッチゲームを作って")

    assert held["pxStop2"] == pytest.approx(held["pxStop1"], abs=1e-9)
    assert held["pxEdge"] == 0.0, "a long hold walked out of the field"
