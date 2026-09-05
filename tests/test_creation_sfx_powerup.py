"""The step-up does not sound like the 47th gem (§2, C-1339).

sfxr's palette keeps powerUp apart from pickupCoin for a reason: the
multiplier rising is rare and earned, and it gets a rising tone WITH
vibrato - an LFO wired into the oscillator's frequency. These tests read
the wiring off each combo template's driven page, the way C-1308 taught:
connections, not constructions, because an LFO that is built and never
wired shaped nothing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.combo import COMBO_TEMPLATES
from sidra_ai.creation.audio import probe_source
from sidra_ai.creation.games import generate_game

_REQUESTS = {
    "catch": "キャッチゲームを作って",
    "shooter": "シューティングゲームを作って",
    "marble": "玉転がしゲームを作って",
    "fishing": "釣りゲームを作って",
}


def _heard(request: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game(request).html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=probe_source(script.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("template", sorted(COMBO_TEMPLATES))
def test_the_cheer_rings_a_vibrato_and_the_gem_does_not(template: str) -> None:
    heard = _heard(_REQUESTS[template])

    cheer = heard["cheerNodes"]
    assert cheer, "the cheer made no sound at all"
    assert "lfo->frequency" in cheer, "the step-up sounds like the 47th gem"
    # The vibrato is a modulator AND a carrier: two oscillators, one of
    # them reaching the other's frequency through a depth gain.
    assert cheer.count("oscillator") == 2
    assert "lfo->frequency" not in heard["gemNodes"], (
        "the pickup grew a vibrato too, so the step-up is not distinct"
    )
    assert heard["gemNodes"] == ["oscillator"]


def test_the_mute_silences_the_step_up_too() -> None:
    heard = _heard(_REQUESTS["marble"])

    assert heard["powerupMutedNodes"] == 0


def test_the_milestones_ring_power_and_the_key_stays_plain() -> None:
    """C-1346: lantern, shrine and charm are powers; the key is a lock's."""

    from sidra_ai.creation.adventure import milestone_probe
    from sidra_ai.creation.platformer import lamp_sfx_probe

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")

    page = generate_game("迷宮を冒険するゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    run = subprocess.run(
        ["node", "-"], input=milestone_probe(script.group(1)),
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    adv = json.loads(run.stdout.strip().splitlines()[-1])
    assert adv["heartsAfter"] > 3 and "lfo->frequency" in adv["shrineNodes"]
    assert adv["charmHeld"] and "lfo->frequency" in adv["charmNodes"]
    assert adv["keyHeld"] and "lfo->frequency" not in adv["keyNodes"]

    page = generate_game("ジャンプで進むゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    run = subprocess.run(
        ["node", "-"], input=lamp_sfx_probe(script.group(1)),
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stderr[:400]
    plat = json.loads(run.stdout.strip().splitlines()[-1])
    assert plat["lampLit"] and "lfo->frequency" in plat["lampNodes"]
