"""The monster's biggest blow had one beat out of three (§6 観察 2, C-1615).

The film reads a hit as three beats: a flash, smoke that stays after the
flash is gone, and the silhouette coming back out of the smoke. C-1343
gave those to adventure's guard, borrowing "kaiju's own numbers". The
creature the section is actually about had them on the leg and only the
flash on the head - the blow that turns a cycle and, on the third, wins.
Every other channel was already heavier for it: shake 3→7, hitstop 4→6.

The head's smoke is the leg's 34 raised by the same ratio the flash is
(12/8 → 51), and it hangs where the blow landed rather than at the leg's
height, which has to be caught at the moment of the hit because the head
retreats off-screen on the next line.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.kaiju import beats_probe

_SEEN: dict[str, dict] = {}


def _fight() -> dict:
    if not _SEEN:
        html = generate_game("巨大怪獣と戦うゲームを作って").html
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        run = subprocess.run(
            ["node", "-"],
            input=beats_probe(script),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert run.returncode == 0, run.stderr[:400]
        _SEEN.update(json.loads(run.stdout.strip().splitlines()[-1]))
    return _SEEN


@pytest.mark.parametrize("which", ["leg", "head"])
def test_both_blows_land(which: str) -> None:
    assert _fight()[which]["landed"], f"the {which} was never struck"


@pytest.mark.parametrize("which", ["leg", "head"])
def test_both_blows_flash(which: str) -> None:
    assert _fight()[which]["hurtAtHit"] > 0, f"the {which} blow does not flash"


@pytest.mark.parametrize("which", ["leg", "head"])
def test_the_smoke_outlives_the_flash(which: str) -> None:
    """Beat two: it is smoke that STAYS, or it is just a second flash."""

    blow = _fight()[which]
    assert blow["smokeAtHit"] > 0, f"the {which} blow leaves no smoke"
    assert blow["smokeAfterFlash"] >= 15, (
        f"{which}: smoke outlived the flash by only {blow['smokeAfterFlash']} frames"
    )


@pytest.mark.parametrize("which", ["leg", "head"])
def test_the_smoke_clears(which: str) -> None:
    """Beat three: the silhouette comes back out of it."""

    assert _fight()[which]["smokeLeft"] == 0, f"the {which}'s smoke never clears"


def test_the_head_is_the_heavier_blow() -> None:
    """The weighting shake and hitstop already carried."""

    got = _fight()
    assert got["head"]["smokeAtHit"] > got["leg"]["smokeAtHit"], (
        f"head {got['head']['smokeAtHit']} vs leg {got['leg']['smokeAtHit']}"
    )


def test_the_smoke_hangs_where_the_blow_landed() -> None:
    """The head retreats to -160 on the next line, so the height is caught
    at the moment of the hit rather than read back from the boss."""

    got = _fight()
    assert got["leg"]["smokeY"] == got["ground"] - 70
    assert got["head"]["smokeY"] != got["leg"]["smokeY"], (
        "both smokes hang at the leg's height"
    )
    assert got["head"]["smokeY"] < got["leg"]["smokeY"], "the head is above the leg"
