"""The racer's speed is audible (§25, C-1378).

The earliest racing engines were nothing but the RPM driving a square
wave's pitch - "even at this basic level, communicated to the player
their current speed" - while this racer drank the course in silence.
Now a square wave sweeps one octave (55-110Hz, §25's stretch warning)
with the pace, its gain easing off the throttle, under every gate a
sound obeys: the mute key, the volume slider, the playing round.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation import generate_game
from sidra_ai.creation.racing import engine_probe


@pytest.fixture(scope="module")
def heard() -> dict:
    html = generate_game("ゲームを作って", template="racing").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=engine_probe(script),
        capture_output=True, text=True, timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_pitch_follows_the_pace(heard: dict) -> None:
    fast, crawl = heard["fast"], heard["crawl"]
    assert fast["facts"]["on"] and crawl["facts"]["on"]
    assert fast["spd"] > crawl["spd"], "the probe never made a pace difference"
    assert fast["facts"]["freq"] > crawl["facts"]["freq"]


def test_the_throttle_carries_the_gain_too(heard: dict) -> None:
    """§25 事実 2: off throttle, drop the engine layer a few dB."""

    assert heard["fast"]["facts"]["gain"] > heard["crawl"]["facts"]["gain"]


def test_the_sweep_stays_inside_its_octave(heard: dict) -> None:
    f = heard["fast"]["facts"]
    assert f["f0"] <= heard["crawl"]["facts"]["freq"]
    assert f["freq"] <= f["f0"] + f["span"]


def test_the_engine_is_silent_when_nobody_is_racing(heard: dict) -> None:
    assert heard["before"] is False, "the title's attract demo hums"
    assert heard["atGoal"] is False, "the result screen idles"


def test_m_mutes_the_engine_within_a_frame(heard: dict) -> None:
    assert heard["beforeMute"] is True
    assert heard["afterMute"] is False


# --- the marble rolls through the same channel (C-1381) -----------------

from sidra_ai.creation.marble import engine_probe as marble_engine


@pytest.fixture(scope="module")
def rolled() -> dict:
    html = generate_game("ゲームを作って", template="marble").html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=marble_engine(script),
        capture_output=True, text=True, timeout=180,
    )
    assert run.returncode == 0, run.stderr[:400]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_each_act_steps_the_rolling_pitch(rolled: dict) -> None:
    assert rolled["act0"]["on"]
    assert rolled["act0"]["freq"] < rolled["act1"] < rolled["act2"], (
        "the acts accelerate the roll but not the voice"
    )


def test_the_roll_is_silent_when_nobody_is_rolling(rolled: dict) -> None:
    assert rolled["before"] is False, "the title's demo rumbles"
    assert rolled["atEnd"] is False, "the result screen rumbles"


def test_m_mutes_the_roll_within_a_frame(rolled: dict) -> None:
    assert rolled["beforeMute"] is True
    assert rolled["afterMute"] is False
