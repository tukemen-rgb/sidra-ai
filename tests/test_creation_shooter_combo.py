"""C-1411: the shooter's kills carry C-1405's multiplier.

The second template to get the ladder. A kill was already a discrete
success and a hull already ended things, so the rule needed a place to add
points and a place to drop them and nothing else. Every claim here is read
off a flown page: a multiplier that is defined but never paid, or paid but
never drawn, would pass a grep and fail one of these.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.combo import (
    COMBO_MAX,
    COMBO_STEP,
    COMBO_TEMPLATES,
    COMBO_UNWIRED,
    shooter_probe_source,
)
from sidra_ai.creation.games import generate_game


def _fly(**kwargs) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to fly the page")
    page = generate_game("シューティングゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=shooter_probe_source(script.group(1), **kwargs),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:500]
    return json.loads(probe.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def clean() -> dict:
    return _fly(frames=1400)


@pytest.fixture(scope="module")
def crashed() -> dict:
    return _fly(frames=1400, crash_at=400)


def test_the_shooter_is_wired_and_says_so():
    assert "shooter" in COMBO_TEMPLATES
    # "not yet" and "not applicable" are different answers, and a template
    # that got the rule must not still be listed as waiting for it.
    assert "shooter" not in COMBO_UNWIRED


def test_a_clean_flight_climbs_the_ladder(clean):
    assert clean["combo"]["mult"] == COMBO_MAX
    assert clean["kills"] > 0


def test_each_rung_arrives_on_a_multiple_of_the_step(clean):
    kills = [e for e in clean["timeline"] if not e["hit"]]
    for entry, before in zip(kills[1:], kills):
        if entry["mult"] > before["mult"]:
            assert entry["run"] % COMBO_STEP == 0, entry


def test_a_kill_pays_the_rung_it_was_worth(clean):
    # The whole point: a multiplier that is drawn but not paid looks right
    # on screen and changes nothing about the score.
    singles = [e for e in clean["timeline"] if not e["hit"] and e["took"] == 1]
    assert singles, "no frame landed exactly one kill"
    for entry in singles:
        assert entry["gained"] == entry["mult"], entry


def test_a_frame_that_lands_two_kills_pays_for_both(clean):
    # Two shots can meet two hulls on one frame. The payout is then the
    # sum of the rungs those kills stood on, which is bounded by the
    # multiplier before the frame and the one after it - stated as a bound
    # rather than recomputed, because recomputing the ladder here would be
    # the check agreeing with itself.
    for entry in [e for e in clean["timeline"] if not e["hit"] and e["took"] > 1]:
        assert entry["was"] <= entry["mult"], entry
        assert entry["took"] * entry["was"] <= entry["gained"], entry
        assert entry["gained"] <= entry["took"] * entry["mult"], entry


def test_the_multiplier_is_on_screen_from_the_first_kill(clean):
    kills = [e for e in clean["timeline"] if not e["hit"]]
    assert "×1" in (kills[0]["hud"] or "")
    top = [e for e in kills if e["mult"] == COMBO_MAX]
    assert top and f"×{COMBO_MAX}" in (top[0]["hud"] or "")


def test_the_raw_count_survives_beside_the_points(clean):
    # 「撃墜 N 機」 is a count and the score no longer is; keeping both
    # stops the HUD from calling points machines.
    assert clean["kills"] < clean["score"]


def test_graze_is_added_beside_the_run_not_multiplied_into_it(clean):
    assert clean["graze"]["seen"] > 0, "the flight never grazed"
    assert clean["roundScore"] == clean["score"] + clean["graze"]["paid"]


def test_one_hull_takes_the_whole_run(crashed):
    hits = [e for e in crashed["timeline"] if e["hit"]]
    assert hits, "flying into hulls never cost a hit point"
    climbed = [e for e in crashed["timeline"] if e["mult"] > 1]
    assert climbed and climbed[0]["at"] < hits[0]["at"], "nothing was built first"
    assert hits[0]["mult"] == 1
    assert hits[0]["run"] == 0


def test_reduced_motion_keeps_the_sound_and_drops_the_particles(clean):
    quiet = _fly(frames=700, reduced=True)
    loud_rise = [e for e in clean["timeline"] if "powerup" in e["rang"]]
    quiet_rise = [e for e in quiet["timeline"] if "powerup" in e["rang"]]
    assert quiet_rise, "reduced motion lost the sound of the rise"
    assert loud_rise
    assert quiet_rise[0]["rose"] < loud_rise[0]["rose"]
    # The number itself is information, so it is drawn either way.
    assert "×" in (quiet_rise[0]["hud"] or "")
