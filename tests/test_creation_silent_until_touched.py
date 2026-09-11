"""Nothing sounds before the first touch (§2, C-1682).

§2's fact is plain: "ブラウザの自動再生制限があるため、AudioContext は
最初のユーザー操作で resume する". The page implements the gesture half
properly - ``gateGesture()`` flips on the first keydown or pointerdown and
rings there, so the resume happens inside the gesture - but ``sfx()``
itself had no gate, and the attract demo is a recorded hand on the real
controls. Shooter's hand holds the trigger, so ``shoot()`` rang on frame
one of a page nobody had touched.

Measured before fixed, driven for 240 frames with no input: all ten
templates built an AudioContext and started nodes. Every one of those
calls could only fail, and each put an autoplay warning in the visitor's
console.

Nine audio judges already ask whether a sound happens and what it sounds
like. This one asks when it is allowed to - and, in the other direction,
that the press which opens the gate is not itself swallowed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from sidra_ai.creation.audio import gesture_probe
from sidra_ai.creation.games import generate_game

REQUESTS = {
    "adventure": "迷宮を冒険するゲームを作って",
    "duel": "ビームで撃ち合うゲームを作って",
    "shooter": "シューティングゲームを作って",
    "racing": "レースゲームを作って",
    "catch": "落ちものをキャッチするゲームを作って",
}


def _drive(request: str) -> dict:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to drive the page")
    html = generate_game(request).html
    found = re.search(r"<script>(.*?)</script>", html, re.S)
    assert found is not None
    got = subprocess.run(
        ["node", "-"],
        input=gesture_probe(found.group(1)),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert got.returncode == 0, got.stderr[:400]
    return json.loads(got.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def heard() -> dict[str, dict]:
    return {key: _drive(req) for key, req in REQUESTS.items()}


def test_no_page_makes_a_sound_before_it_is_touched(heard: dict[str, dict]) -> None:
    """The defect itself, and the attract demo does not excuse it: a demo
    that shoots is still a page nobody has touched."""

    for key, seen in heard.items():
        before = seen["untouched"]
        assert before["built"] == 0, f"{key}: {before['built']} AudioContext(s)"
        assert before["rang"] == [], f"{key}: {before['rang']}"
        assert before["resumed"] == [], f"{key}: resumed before any gesture"


def test_the_press_that_opens_the_gate_sounds(heard: dict[str, dict]) -> None:
    """The other direction. A gate that rings before it opens would
    swallow its own first sound on every page load, forever, and the
    silence would look exactly like the fix working."""

    for key, seen in heard.items():
        assert seen["atTouch"]["rang"], f"{key}: the first press made no sound"
        assert seen["atTouch"]["built"] == 1, seen["atTouch"]["built"]


def test_play_is_not_silent(heard: dict[str, dict]) -> None:
    """Silence is not a way to pass this."""

    for key, seen in heard.items():
        assert len(seen["after"]["rang"]) > 1, f"{key}: {seen['after']['rang']}"


def test_nothing_is_scheduled_on_a_suspended_context(heard: dict[str, dict]) -> None:
    """§2's rule itself: the context is resumed before a node starts."""

    for key, seen in heard.items():
        assert seen["after"]["resumed"], f"{key}: never resumed"
        assert "suspended" not in seen["after"]["rang"], key


def test_the_gate_lets_a_page_without_one_sound() -> None:
    """``heardYet`` is guarded by ``typeof`` on purpose: a page assembled
    without the start-screen preamble has no gesture to wait for, and
    must not be silenced by a flag that does not exist."""

    from sidra_ai.creation.audio import SFX_PREAMBLE

    assert "function heardYet()" in SFX_PREAMBLE
    assert "typeof GATE_GESTURE==='undefined'" in SFX_PREAMBLE

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required")
    got = subprocess.run(
        ["node", "-"],
        input=(
            "function heardYet(){try{"
            "return typeof GATE_GESTURE==='undefined'||GATE_GESTURE}"
            "catch(e){return true}}\n"
            "console.log(JSON.stringify({noGate: heardYet()}));"
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert got.returncode == 0, got.stderr[:300]
    assert json.loads(got.stdout.strip().splitlines()[-1])["noGate"] is True
