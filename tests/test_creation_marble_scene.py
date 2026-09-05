"""The marble's corridor, judged by rolling it (§7 at course scale, C-1307).

The probe pilots the run - into gates, away from blocks - and reads the
act of the sky off the running page as each third of the course passes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.marble import GATE_BASE, combo_probe_source, probe_source


def _rolled(request: str = "玉転がしゲームを作って") -> dict:
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
        timeout=120,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])


def _combo_events() -> list[dict]:
    """The same corridor, driven by the probe that records the run."""

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    page = generate_game("玉転がしゲームを作って").html
    script = re.search(r"<script>(.*?)</script>", page, re.S)
    assert script is not None
    probe = subprocess.run(
        ["node", "-"],
        input=combo_probe_source(script.group(1), mode="run"),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert probe.returncode == 0, probe.stderr[:400]
    return json.loads(probe.stdout.strip().splitlines()[-1])["events"]


def test_the_course_is_three_acts_and_the_sky_steps_with_the_distance():
    rolled = _rolled()

    assert rolled["sceneEarly"] == 0
    assert rolled["sceneMid"] == 1
    assert rolled["sceneLate"] == 2
    assert rolled["z"] >= rolled["course"] * 2 / 3, "the pilot reached the final act"


def test_the_final_stretch_is_the_brightest_sky_of_the_run():
    rolled = _rolled()
    scenes = rolled["scenes"]

    assert len(scenes) == 3
    assert len({s["floor"] for s in scenes}) == 3, "each act paints its own sky"
    assert scenes[2]["lum"] > scenes[0]["lum"]
    assert scenes[2]["lum"] >= scenes[1]["lum"]


def test_the_pilot_actually_plays_the_course():
    """Gates rolled through, not merely frames survived: the probe steers."""

    rolled = _rolled()

    assert rolled["state"] == "over"
    assert rolled["gates"] >= 10


def test_the_course_reaccelerates_by_thirds():
    """§6 観察 3 at course scale (C-1314): each act rolls faster than the last."""

    rolled = _rolled()
    rates = rolled["rates"]

    assert len(rates) == 3
    assert min(rates) > 0, "every act was actually rolled through"
    assert rates[0] < rates[1] < rates[2], "the pace steps up with the sky"
    assert rates[2] >= rates[0] * 1.2, "the final stretch is clearly the fastest"
    assert rolled["state"] == "over", "the faster course still completes"


def test_completing_the_course_fires_the_win_beat_once():
    """§1/§6 (C-1316): the run-in under the brightest sky ends on the
    heaviest beat of the round - and never on the failure's."""

    rolled = _rolled()

    assert rolled["state"] == "over"
    assert rolled["winBeats"] == 1
    assert rolled["failBeats"] == 0


def test_hot_gates_stand_in_a_blocks_shadow_and_pay_double():
    """§13 事実 1 (C-1313): optional danger, rewarded - and honest arithmetic.

    The arithmetic here used to read ``gates + hotTaken`` - every gate worth
    its base, the hot ones worth it twice. C-1420 put a run multiplier on
    the corridor and that sum stopped being the whole story, so this states
    the same claim in the form the game now uses: **a hot gate is worth the
    base again on top of whatever the run was paying**, added outside the
    multiplier rather than compounded with it.

    That is still C-1313's claim, and it is the part C-1420 was careful to
    keep: the extra for taking the risk does not change with the run, so
    「この門は 1 点多い」 stays true at x1 and at x4 alike.
    """

    rolled = _rolled()

    assert rolled["hotTotal"] >= 2, "the course offers real optional danger"
    assert rolled["hotTaken"] >= 1, "the pilot found the risk worth taking"
    assert rolled["state"] == "over", "the risk is optional; the run still ends"

    # Driven again through the combo probe, which records the multiplier
    # that was live for each gate - the piece the scene probe cannot see.
    events = [e for e in _combo_events() if e["kind"] == "through"]
    assert events, "the roll went through no gates"
    hot = [e for e in events if e["hot"]]
    assert hot, "no hot gate was taken, so the double is untested"
    for event in events:
        base_pay = GATE_BASE * event["mult"]
        assert event["paid"] == base_pay + (GATE_BASE if event["hot"] else 0), event
    # ...and the extra is flat: the same one point whatever the run.
    assert {e["paid"] - GATE_BASE * e["mult"] for e in hot} == {GATE_BASE}
