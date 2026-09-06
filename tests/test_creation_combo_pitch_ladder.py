"""The combo ladder has an altitude (§2→§14 事実 1 の第 3 形, C-1359).

Every rung-up used to cheer at the table's one pitch, so ×2 and ×4 were
indistinguishable by ear. Each rung now cheers two semitones above the
last - wide enough that the ±4% playback jitter can neither fake a step
nor hide one.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.combo import COMBO_TEMPLATES, ladder_probe
from sidra_ai.creation.games import generate_game

STEP = 2 ** (1 / 6)


@pytest.fixture(scope="module")
def climbed() -> dict[str, dict]:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    out: dict[str, dict] = {}
    for key in COMBO_TEMPLATES:
        page = generate_game("ゲームを作って", template=key).html
        script = re.search(r"<script>(.*?)</script>", page, re.S)
        assert script is not None, key
        probe = subprocess.run(
            ["node", "-"],
            input=ladder_probe(script.group(1)),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert probe.returncode == 0, f"{key}: {probe.stderr[:400]}"
        out[key] = json.loads(probe.stdout.strip().splitlines()[-1])
    return out


@pytest.mark.parametrize("key", COMBO_TEMPLATES)
def test_each_rung_cheers_once_and_higher(climbed: dict, key: str) -> None:
    seen = climbed[key]
    rungs = [ch["rung"] for ch in seen["cheers"]]
    assert rungs == list(range(2, seen["max"] + 1))
    heard = [ch["fs"][0] for ch in seen["cheers"]]
    assert all(a < b for a, b in zip(heard, heard[1:])), heard


@pytest.mark.parametrize("key", COMBO_TEMPLATES)
def test_each_cheer_sits_in_its_own_band(climbed: dict, key: str) -> None:
    """Bands are set by the page's own table, and adjacent ones never touch."""

    seen = climbed[key]
    base, jit = seen["base"], seen["jitter"]
    assert base * (1 + jit) < base * STEP * (1 - jit), "a jitter could fake a rung"
    for cheer in seen["cheers"]:
        centre = base * STEP ** (cheer["rung"] - 2)
        assert centre * (1 - jit - 1e-9) <= cheer["fs"][0] <= centre * (1 + jit + 1e-9)


@pytest.mark.parametrize("key", COMBO_TEMPLATES)
def test_the_mute_silences_the_altitude_but_not_the_ladder(
    climbed: dict, key: str
) -> None:
    seen = climbed[key]
    assert seen["mutedFreqs"] == 0
    assert seen["mutedRungs"] == list(range(2, seen["max"] + 1))
