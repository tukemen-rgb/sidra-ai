"""A mashed round still ends (C-1500).

Hitstop skips the tick but not the key handlers. In the fishing template -
the default every declined request falls back to - the sweep marker was
still parked inside the zone it just scored in while the world was frozen,
so every further press landed another hit and re-armed the stop before a
single tick could run. Mashing the one action key froze the round clock
for as long as the finger lasted (measured: 183ms of round time across
100 wall seconds) while the score climbed without bound.

The fix is one cast per drawn frame: CAST_ARMED is set by step() - which
hitstop skips - and spent by cast(). Guarding on HITSTOP alone was
measured insufficient: the press landing on the exact frame the stop
expires re-freezes a world that still has not moved.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.adapt import STREAK_PROBE  # noqa: E402
from sidra_ai.creation.games import generate_game  # noqa: E402

_PROBE_TAIL = "run(2); press(' '); run(2);"


def _mash_fishing(frames: int) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the round")
    found = re.search(
        r"<script>(.*?)</script>", generate_game("釣りゲームを作って").html, re.S
    )
    assert found is not None
    probe = STREAK_PROBE.replace("SCRIPT_PLACEHOLDER", found.group(1)).replace(
        "STORED_INPUT", "{}"
    )
    source = probe.split(_PROBE_TAIL)[0] + _PROBE_TAIL + (
        """
let frames = 0;
for (; frames < %d && !roundEnded() && !ROUND_DONE; frames++) { press(' '); run(1) }
run(8);
const f = fishFacts();
console.log(JSON.stringify({ frames: frames, ended: roundEnded() || ROUND_DONE,
  ms: f.ms, score: f.score, hits: f.hits, casts: f.casts,
  banked: ROUND_BANKED, final: ROUND_FINAL }));
"""
        % frames
    )
    run = subprocess.run(
        ["node", "-"], input=source, capture_output=True, text=True, timeout=240
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_a_mashed_fishing_round_ends_on_its_clock() -> None:
    """Pre-fix: 6000 mashed frames left the round clock at 183ms."""

    played = _mash_fishing(6000)

    assert played["ended"], "the mashed round never reached its end"
    assert played["frames"] <= 5000, "the round overran the probe budget"
    assert played["banked"], "the finished round banked nothing"


def test_a_mashed_round_scores_at_most_one_hit_per_moving_frame() -> None:
    """The unbounded half of the exploit: frozen-marker hits cost no time,
    so the score had no ceiling. One cast per drawn frame restores one."""

    played = _mash_fishing(6000)

    # Every hit now spends at least one tick, so hits can never exceed the
    # frames the round ran. Pre-fix the same drive measured 2,990 hits
    # against 11 ticks of round time.
    assert played["hits"] <= played["frames"]
    # And the casts the freeze swallowed are not misses: the combo rule
    # (C-1426) still only charges for a cast that actually happened.
    assert played["casts"] <= played["frames"] + 1
