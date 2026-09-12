"""A low camera, and something small standing in the frame (§6 観察 1,
C-1706).

The observation is one sentence carrying four instructions: 「巨大さは
全身を見せないことで作られる……小さい存在と同じフレームに入れて対比
する。カメラは低い」. Two of them were held - ``creation_whole_body_is_rare``
counts the frames in which the head fits, and the awakening judge notes
the wide shot - and both count *events*.

The other two are geometry, and geometry had no instrument. Raise
``GROUND`` to mid-frame, or draw the walker three times its size, and
every judge above stays green while the giant stops reading as giant.

Read from the page's own ``frameFacts()``, built out of the same
constants ``draw()`` uses, so the picture and the judge cannot drift
(the C-1342 rule). Read twice, because the frame changes: standing, with
the head off the top of the canvas, and again once the leg is shot open
and the head comes down.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.kaiju import frame_probe

HORIZON_LOW = 0.75  # the ground line sits this far down the frame
HORIZON_FLOOR = 0.05  # but not on the bottom edge: ground still shows
WALKER_SMALL = 0.15  # the walker is drawn no taller than this
CONTRAST = 3.0  # and the creature fills this much more of it


@pytest.fixture(scope="module")
def frames() -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to raise the creature")
    page = generate_game("巨大怪獣と戦うゲームを作って").html
    found = re.search(r"<script>(.*?)</script>", page, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=frame_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


def visible(shot: dict) -> float:
    """What is on screen of the creature: horizon up to its head, or up
    to the top edge while the head is still above the canvas."""

    head = shot["headNow"]
    return shot["ground"] - max(0.0, float(0 if head is None else head))


def test_both_frames_were_reached(frames: dict) -> None:
    assert frames["phase"] == "open", frames["phase"]
    assert frames["standing"]["headNow"] < 0, "the head fitted while standing"
    assert frames["opened"]["headNow"] > 0, "the head never came down"


@pytest.mark.parametrize("when", ["standing", "opened"])
def test_the_camera_is_low(frames: dict, when: str) -> None:
    """The fourth instruction of the sentence, and the one nothing read."""

    shot = frames[when]
    assert shot["ground"] / shot["h"] >= HORIZON_LOW, (
        when,
        shot["ground"],
        shot["h"],
    )


@pytest.mark.parametrize("when", ["standing", "opened"])
def test_something_small_stands_in_the_frame(frames: dict, when: str) -> None:
    shot = frames[when]
    assert shot["meHeight"] > 0, when
    assert shot["meHeight"] / shot["h"] <= WALKER_SMALL, (
        when,
        shot["meHeight"],
        shot["h"],
    )


@pytest.mark.parametrize("when", ["standing", "opened"])
def test_the_contrast_is_in_the_same_frame(frames: dict, when: str) -> None:
    """「小さい存在と同じフレームに入れて対比する」- both halves of the
    contrast have to be on screen at once, which is why this is measured
    against the walker drawn beside it and not against a constant."""

    shot = frames[when]
    assert visible(shot) / shot["meHeight"] >= CONTRAST, (
        when,
        visible(shot),
        shot["meHeight"],
    )


def test_low_is_not_satisfied_by_a_frame_with_no_sky(frames: dict) -> None:
    """The other direction of「カメラは低い」. A horizon pushed to the
    bottom edge passes the test above and leaves the walker standing on
    nothing: no floor receding away, no camera, just a wall. Low is a
    position, not a maximum."""

    for when in ("standing", "opened"):
        shot = frames[when]
        floor = (shot["h"] - shot["ground"]) / shot["h"]
        assert floor >= HORIZON_FLOOR, (when, floor, shot["ground"], shot["h"])


def test_the_box_the_judge_reads_is_the_box_the_page_draws(frames: dict) -> None:
    """The walker's height was two literals inside ``draw()``. Named once,
    the picture and ``frameFacts()`` move together - change the drawing
    and the judge notices, which is the whole point of measuring the
    geometry rather than the events."""

    from sidra_ai.creation import kaiju

    assert (
        "const ME_BODY_H=18,ME_TURRET_H=12,ME_BODY_Y=30,ME_TURRET_Y=42;"
        in kaiju.KAIJU_SCRIPT
    )
    assert "GROUND-ME_BODY_Y*sq,32*sqw,ME_BODY_H*sq" in kaiju.KAIJU_SCRIPT
    assert "GROUND-ME_TURRET_Y*sq,8*sqw,ME_TURRET_H*sq" in kaiju.KAIJU_SCRIPT
    assert "GROUND-30*sq,32*sqw,18*sq" not in kaiju.KAIJU_SCRIPT
    drawn = 42 - (30 - 18)  # turret top down to the body's bottom edge
    assert frames["standing"]["meHeight"] == drawn == 30
