"""The last seconds have to reach the ear too (C-1448).

``roundFacts().urgent`` has existed since C-1417 and nothing listened to
it: the countdown was on the screen (C-1417) and the round's ending was in
the hand (C-1413), while the audio table had no voice for the clock at all.

Everything here is read off a page actually driven for a whole go in node,
never off the source, and the tick is read as TWO facts: what the page
asked for (``sfx`` is bracketed, not replaced) and what it built (a
recording AudioContext underneath). The pair is the point - a count of
calls alone would pass a page that shouts through the mute, and a count of
nodes alone could not tell that page from one whose clock never ticks.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.audio import PREAMBLE_NAMES, SFX_PREAMBLE
from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.round import ROUND_URGENT_MS, tick_probe_source

#: Held off the road, racing is still going when the buzzer arrives. Same
#: reason - and same value - as the countdown judge in product_metrics.py.
HOLD = {"racing": "ArrowLeft"}

#: The whole-second marks inside the urgent window, newest first.
SECONDS = sorted(range(1, ROUND_URGENT_MS // 1000 + 1), reverse=True)

#: Three templates that reach the buzzer unattended, so the situation the
#: tick exists for actually happens. Not all ten: a page takes ~20s to
#: drive, and the judge measures the full set every run.
REACHES_THE_END = ("catch", "fishing", "platformer")


def drive(template: str, **kw):
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=tick_probe_source(body, hold=HOLD.get(template, ""), **kw),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def ticks(run):
    return [
        dict(call, left=frame["left"], remain=frame["remain"], urgent=frame["urgent"])
        for frame in run["frames"]
        for call in frame["calls"]
        if call["name"] == "tick"
    ]


@pytest.fixture(scope="module")
def played():
    return {key: drive(key) for key in REACHES_THE_END}


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_the_clock_ticks_once_for_each_of_the_last_seconds(template, played):
    heard = ticks(played[template])
    # A list, not a set: a second that ticked twice has to fail here rather
    # than disappear into the count.
    assert [t["left"] for t in heard] == SECONDS


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_nothing_ticks_before_the_last_seconds(template, played):
    heard = ticks(played[template])
    assert [t for t in heard if not t["urgent"]] == []
    assert all(t["remain"] <= ROUND_URGENT_MS for t in heard)


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_the_ticks_are_about_a_second_apart(template, played):
    """The gap is the information: 「1 秒に 1 回」 is a rate, not a count."""

    heard = ticks(played[template])
    gaps = [
        heard[i]["remain"] - heard[i + 1]["remain"] for i in range(len(heard) - 1)
    ]
    # One frame of slack either way (60fps), because the tick lands on the
    # first frame of each new whole second rather than on its boundary.
    assert gaps and all(980 <= gap <= 1020 for gap in gaps), gaps


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_the_tick_actually_reaches_the_audio_device(template, played):
    # Without this the three calls above could all be returning at the door.
    assert all(t["built"] > 0 for t in ticks(played[template]))


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_the_tick_never_climbs(template, played):
    """条件③: a clock, not a nag.

    Escalation would arrive as a pitch on the call - that is the only way
    this table's voices can be bent - so a tick that leant on the player
    would show a rising number here. Whether the buzzer is a break or a
    defeat is the owner's question (C-1127), and a rising tick answers it.
    """

    assert {t["pitch"] for t in ticks(played[template])} == {None}


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_muting_silences_the_tick_without_stopping_the_clock(template):
    """条件①. Both halves matter, and they are different halves.

    A page that keeps ticking through M is shouting over the operator; a
    page that stops COUNTING when muted has turned a mute into a feature
    switch. The calls must stay, the sound must go.
    """

    quiet = drive(template, mute=True)
    heard = ticks(quiet)
    assert [t["left"] for t in heard] == SECONDS
    assert all(t["built"] == 0 for t in heard)
    # Not only the tick: M is the whole page's mute.
    assert not any(
        call["built"] for frame in quiet["frames"] for call in frame["calls"]
    )


@pytest.mark.parametrize("template", REACHES_THE_END)
def test_the_volume_dial_at_zero_silences_it_too(template):
    """条件①'s other half: the listener's own dial (C-1408), not just M."""

    quiet = drive(
        template, store={f"sidra.tune.{template}": json.dumps({"volume": 0})}
    )
    heard = ticks(quiet)
    assert [t["left"] for t in heard] == SECONDS
    assert all(t["built"] == 0 for t in heard)


def test_the_tick_is_the_flattest_voice_in_the_table():
    """The sound itself cannot climb either: it starts and ends on one note.

    Every other effect sweeps - that sweep is how a pickup reads as a
    pickup. The tick is the only entry whose two ends are equal, which is
    what makes it a clock rather than an alarm.
    """

    spec = re.search(r"tick:\['(\w+)',([\d.]+),([\d.]+),", SFX_PREAMBLE)
    assert spec, "the tick voice is not in the table"
    wave, start, end = spec.group(1), float(spec.group(2)), float(spec.group(3))
    assert wave != "noise"
    assert start == end, f"the tick sweeps {start}->{end}"


def test_the_tick_is_part_of_the_shared_vocabulary():
    # A private sound is how a drawer becomes ten drawers.
    assert "tick" in PREAMBLE_NAMES


def test_every_template_carries_the_tick_even_the_short_ones():
    """The tick lives in the shared round preamble, not in a template.

    Templates that end before the buzzer never reach the urgent window,
    but a page that could not tick at all would be a different product -
    so what is checked is that the mechanism ships everywhere.
    """

    for key in sorted(TEMPLATES):
        page = generate_game("ゲームを作って", template=key).html
        assert "roundTickSound()" in page, key
        assert "tick:['triangle'" in page, key
