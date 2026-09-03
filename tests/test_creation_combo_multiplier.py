"""Consecutive successes pay more, and the page never hides the number.

§13 事実 2: every template scored one point per thing, so a careful round
and a greedy one came out the same. The assertions here are as much about
restraint as about the reward - the multiplier is capped, one miss takes
all of it, and it is on screen at ×1 as much as at ×4, because a bonus a
player only meets when it fires is a slot machine.

Driven rather than grepped: the basket is steered onto the next item to
force a catch, or away from it to force a miss, and the page's own
``comboFacts()``, score and HUD line are read back.
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

from sidra_ai.creation.combo import (  # noqa: E402
    COMBO_MAX,
    COMBO_STEP,
    COMBO_TEMPLATES,
    COMBO_UNWIRED,
    PREAMBLE_NAMES,
    probe_source,
)
from sidra_ai.creation.games import TEMPLATES, generate_game  # noqa: E402

WIRED = COMBO_TEMPLATES[0]


def _script(request: str = "キャッチゲームを作って") -> str:
    found = re.search(r"<script>(.*?)</script>", generate_game(request).html, re.S)
    assert found is not None, "the generated page has no script"
    return found.group(1)


def _play(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to play the rounds")
    run = subprocess.run(
        ["node", "-"],
        input=probe_source(_script(), **kwargs),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert run.returncode == 0, run.stderr.strip()[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------ the bookkeeping


def test_every_template_is_either_wired_or_has_a_reason() -> None:
    """"Not yet" and "not applicable" are different answers, and only the
    first is a backlog item. Neither is allowed to be silence."""

    assert set(COMBO_TEMPLATES) | set(COMBO_UNWIRED) == set(TEMPLATES)
    assert not set(COMBO_TEMPLATES) & set(COMBO_UNWIRED)
    assert all(reason.strip() for reason in COMBO_UNWIRED.values())


def test_the_preamble_reaches_only_the_wired_template() -> None:
    for name in PREAMBLE_NAMES:
        assert name in generate_game("キャッチゲームを作って").html
    assert "comboMult" not in generate_game("対戦ゲームを作って").html


# ------------------------------------------------------------------ the rule


def test_a_clean_run_climbs_the_ladder_and_stops() -> None:
    seen = _play(frames=1200)
    rungs = {row["caught"]: row["mult"] for row in seen["timeline"] if row["missed"] == 0}

    assert rungs, "nothing was caught at all"
    for caught, mult in rungs.items():
        assert mult == min(COMBO_MAX, 1 + caught // COMBO_STEP), (caught, mult)
    assert max(rungs.values()) == COMBO_MAX, "a clean run never reached the top"


def test_the_multiplier_is_capped() -> None:
    """Past the cap the last catch of a round outweighs the first thirty,
    which stops being a score."""

    seen = _play(frames=1200)

    assert seen["facts"]["mult"] == COMBO_MAX
    assert seen["facts"]["run"] > COMBO_STEP * COMBO_MAX


def test_one_miss_takes_all_of_it() -> None:
    """No decay and no grace frame: a run with a cushion is not a run."""

    seen = _play(frames=1200, misses=[COMBO_STEP * COMBO_MAX])
    after = [row for row in seen["timeline"] if row["missed"] == 1]

    assert after, "the deliberate miss never landed"
    assert after[0]["mult"] == 1
    assert after[0]["run"] == 0


def test_the_run_rebuilds_after_a_miss() -> None:
    """Taking it away for good would be a punishment, not a reset."""

    seen = _play(frames=1200, misses=[COMBO_STEP])
    after = [row for row in seen["timeline"] if row["missed"] == 1]

    assert any(row["mult"] > 1 for row in after[1:])


def test_the_points_are_not_the_count() -> None:
    seen = _play(frames=1200)

    assert seen["score"] > seen["caught"] > 0


# ------------------------------------------------------------ what it says


def test_the_number_is_on_screen_at_every_rung() -> None:
    """Including ×1. A multiplier a player only learns about when it fires
    is a slot machine; one they can watch is a decision."""

    seen = _play(frames=1200)
    drawn = {row["mult"]: row["hud"] for row in seen["timeline"]}

    assert set(drawn) == set(range(1, COMBO_MAX + 1))
    for mult, hud in drawn.items():
        assert hud and f"×{mult}" in hud, (mult, hud)


def test_the_raw_count_stays_beside_the_points() -> None:
    """「得点」 must not be readable as the number of things caught."""

    seen = _play(frames=600)
    hud = seen["timeline"][-1]["hud"]

    assert "得点" in hud and "受け" in hud and "こぼし" in hud


def test_reduced_motion_keeps_the_news_and_drops_the_confetti() -> None:
    """C-1020's rule, not a new one: decoration goes, information stays."""

    loud = _play(frames=600)
    calm = _play(frames=600, reduced=True)
    rises = [row for row in loud["timeline"] if "gem" in row["rang"]]
    quiet_rises = [row for row in calm["timeline"] if "gem" in row["rang"]]

    assert rises and quiet_rises, "the rise made no sound at all"
    assert len(quiet_rises) == len(rises), "reduced motion changed the ladder"
    assert max(row["rose"] for row in quiet_rises) < min(row["rose"] for row in rises)


def test_the_fall_is_not_celebrated() -> None:
    """Losing the run is punishment enough."""

    seen = _play(frames=1200, misses=[COMBO_STEP * 2])
    lost = [row for row in seen["timeline"] if row["missed"] == 1][0]

    assert "gem" not in lost["rang"]
