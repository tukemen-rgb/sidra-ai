"""A phone must be able to pause, not only to un-pause (C-1451).

Pause had exactly one entrance: the P key. The canvas ``pointerdown``
handler leads to ``gateStart`` or ``gateGesture`` and nowhere else, so on a
device with no keyboard the door was one-way - a tap on a paused game
counts as "start" and resumes it, but nothing could ever pause one. §18 says
the phone is the viewing environment that matters, and a phone is also where
the interruption happens.

Everything here is driven by taps at canvas coordinates rather than by
calling the page's own functions: the claim is that a thumb can reach it.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.round import ROUND_CLOCK_BOX
from sidra_ai.creation.touchpad import (
    PAD_KEYS,
    keys_read,
    touch_pause_probe_source,
    unreachable_keys,
)

#: Three templates, driven fully. The judge measures all ten each run; a
#: page takes a few seconds to build and drive, and the mechanism lives in
#: the shared pad rather than in any template.
SOME = ("catch", "platformer", "fishing")


def drive(template: str, **kw):
    page = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    done = subprocess.run(
        ["node", "-"],
        input=touch_pause_probe_source(body, **kw),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-600:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def runs():
    return {key: drive(key) for key in SOME}


def steps(run):
    return {step["what"]: step for step in run["seen"]}


@pytest.mark.parametrize("template", SOME)
def test_a_finger_can_pause_a_running_game(template, runs):
    """The whole point: title -> tap -> playing -> tap P -> paused."""

    seen = steps(runs[template])
    assert seen["atLoad"]["gate"] == "title"
    assert seen["playing"]["gate"] == "playing"
    assert seen["afterPauseTap"]["gate"] == "paused"


@pytest.mark.parametrize("template", SOME)
def test_the_tap_that_already_resumed_still_resumes(template, runs):
    """条件②. The new door must not have closed the old one."""

    assert steps(runs[template])["afterResumeTap"]["gate"] == "playing"


@pytest.mark.parametrize("template", SOME)
def test_no_pause_button_on_the_title_screen(template, runs):
    """条件①: 「any key」 has to mean any key, and the same for taps.

    P itself is ignored on the title for this reason; a button that only
    appears there to be pressed by accident would reintroduce it.
    """

    seen = steps(runs[template])
    assert seen["atLoad"]["pause"] is None
    assert seen["playing"]["pause"] is not None


@pytest.mark.parametrize("template", SOME)
def test_the_button_is_drawn_where_it_is_hit(template, runs):
    """An invisible hit target is a trap, not a control."""

    run = runs[template]
    button = run["button"]
    drawn = [
        op
        for op in steps(run)["playing"]["painted"]
        if op["kind"] == "rect"
        and abs(op["x"] - round(button["x"])) <= 1
        and abs(op["y"] - round(button["y"])) <= 1
    ]
    assert drawn, button


@pytest.mark.parametrize("template", SOME)
def test_the_button_stays_on_the_canvas_and_off_the_countdown(template, runs):
    """Measured against the badge's own numbers, not against a screenshot.

    C-1417's countdown owns the band under the HUD row on the right, which
    is the same column this button sits in.
    """

    run = runs[template]
    button, canvas = run["button"], run["canvas"]
    assert 0 <= button["x"] and button["x"] + button["w"] <= canvas["w"]
    assert 0 <= button["y"] and button["y"] + button["h"] <= canvas["h"]
    assert button["y"] >= ROUND_CLOCK_BOX[1] + ROUND_CLOCK_BOX[3], button


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_button_ships_with_every_template(template):
    """It lives in the shared pad, so it cannot be a per-template favour."""

    page = generate_game("ゲームを作って", template=template).html
    assert "padPauseButton()" in page


def test_pause_is_sent_as_a_key_not_as_a_call():
    """One definition of pause, and one job for the pad.

    The button synthesises the P key rather than calling gateTogglePause,
    so the keyboard and the finger cannot come to mean different things -
    that half is behaviour, and break-testing it (ignoring the press)
    fails the round trip above.

    The ``KeyP`` half is a convention, not a behaviour, and is written down
    as such: the gate reads ``e.key``, so measured, dropping ``KeyP`` from
    the code map changes nothing a player could see. It is pinned because
    every other pad key carries its real ``code``, and a synthetic event
    that lies about one is a trap for the next template that reads it.
    """

    from sidra_ai.creation.touchpad import PAD_PREAMBLE

    # The comments explain the choice by naming the function, so read the
    # code with them stripped rather than the file as written.
    code = re.sub(r"/\*.*?\*/", "", PAD_PREAMBLE, flags=re.S)
    assert "gateTogglePause" not in code
    assert "KeyP" in code


def test_p_is_not_treated_as_a_control_a_template_reads():
    """C-1244's filter is about the keys the TEMPLATE reads; P is the page's.

    If P leaked into that vocabulary, either the pad would start drawing it
    per-template or `creation_touch_playable` would start reporting a
    phone-unreachable key that no game has.
    """

    assert "p" not in PAD_KEYS
    for key in sorted(TEMPLATES):
        script = TEMPLATES[key].script
        assert "p" not in keys_read(script), key
        assert unreachable_keys(script) == set(), key
