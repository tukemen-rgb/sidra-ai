"""C-1766: every exit releases the pad, and nothing else does.

§22 has two halves built from the same research. ``focusRelease`` lifts the
keyboard's held keys and has listened to all three signals since C-1373;
its own comment says hidden is the tab switch and the phone's home screen.
``padRelease`` lifts the pad's - and had blur and pagehide only. The one
surface that exists only for phones was the half missing the phone's
signal.

Left that way the pad kept a button lit for a finger that was gone, and -
because the draw loop advances the restart hold every frame whether or not
anything is touching - a run whose player went to the home screen with a
finger on R came back and restarted itself.

The control case is not decoration: an implementation that released
unconditionally would satisfy all three exits and make the pad unusable.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.focus import FOCUS_PREAMBLE  # noqa: E402
from sidra_ai.creation.games import generate_game  # noqa: E402
from sidra_ai.creation.touchpad import (  # noqa: E402
    EXIT_SIGNALS,
    PAD_PREAMBLE,
    padexit_probe,
)

TEMPLATES = ("marble", "platformer", "fishing")
INTERRUPTIONS = ("blur", "pagehide", "hidden")


def _script(template: str) -> str:
    html = generate_game("ゲームを作って", template=template).html
    body = re.search(r"<script>(.*?)</script>", html, re.S)
    assert body is not None
    return body.group(1)


def _drive(template: str, signal: str) -> dict:
    out = subprocess.run(
        ["node", "-"], input=padexit_probe(_script(template), signal=signal),
        capture_output=True, text=True, timeout=180,
    )
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------------- the three exits


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("signal", INTERRUPTIONS)
def test_an_interrupted_touch_is_released(template: str, signal: str) -> None:
    seen = _drive(template, signal)

    assert seen["heldBefore"] == 1, "the touch never registered"
    assert seen["plateBefore"] == "held"
    assert seen["heldAfter"] == 0, f"{signal} left the button held"
    assert seen["upSent"] >= 1, f"{signal} sent no keyup, so the game keeps the key"
    assert seen["plateAfter"] == "plate", f"{signal} left the button painted held"


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("signal", INTERRUPTIONS)
def test_a_run_does_not_restart_itself_after_an_exit(template: str, signal: str) -> None:
    """Forty frames pass with nothing touching the screen."""

    seen = _drive(template, signal)

    assert seen["hasR"], "this pad has no restart button to hold"
    assert seen["restarts"] == 0, (
        f"after {signal}, the run restarted itself {seen['restarts']} time(s)"
    )


# ------------------------------------------------------- the other way


@pytest.mark.parametrize("template", TEMPLATES)
def test_nothing_is_released_when_nothing_happened(template: str) -> None:
    seen = _drive(template, "none")

    assert seen["heldAfter"] == 1, "the pad let go with no interruption"
    assert seen["upSent"] == 0
    assert seen["plateAfter"] == "held"


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_hold_that_really_is_held_still_restarts(template: str) -> None:
    """The pad has to keep working. Without this, "release always" scores
    full marks on every exit above."""

    seen = _drive(template, "none")

    assert seen["restarts"] == 1, "a real full hold no longer restarts"


# ----------------------------------------------------- the two halves


def test_both_halves_of_the_contract_listen_for_the_same_three_signals() -> None:
    """Written as an independent expectation rather than by comparing the
    two preambles to each other: if they only had to agree, deleting the
    signal from both would keep them agreeing and wrong (C-1342)."""

    for name, preamble in (("focus", FOCUS_PREAMBLE), ("pad", PAD_PREAMBLE)):
        for signal in ("blur", "pagehide", "visibilitychange"):
            assert signal in preamble, f"{name} does not listen for {signal}"


def test_the_probe_offers_a_control_case() -> None:
    assert set(EXIT_SIGNALS) == {"blur", "pagehide", "hidden", "none"}
    assert EXIT_SIGNALS["none"] == ""
